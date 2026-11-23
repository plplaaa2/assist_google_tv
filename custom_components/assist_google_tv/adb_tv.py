"""Discover, verify, and select ADB TV inputs; related: config_flow.py and app_tools.py."""

import asyncio
import re
from xml.etree import ElementTree

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

TV_INPUT_DUMP = "dumpsys tv_input"
READ_INPUT_MENU = (
    "ui_file=$(mktemp /data/local/tmp/assist-google-tv.XXXXXX) || exit; "
    "trap 'rm -f \"$ui_file\"' EXIT; uiautomator dump \"$ui_file\" >/dev/null && cat \"$ui_file\""
)
SHUTDOWN_COMMAND = (
    "command -v nohup >/dev/null && svc power help 2>&1 | grep -q 'svc power shutdown' || exit 1; "
    "nohup sh -c 'sleep 2; svc power shutdown' </dev/null >/dev/null 2>&1 & "
    "printf 'shutdown_scheduled\\n'"
)


async def async_adb_output(hass, entity_id: str, command: str, context=None) -> str:
    """Return the requested TV's ADB output from the Home Assistant action."""
    if not hass.services.has_service("androidtv", "adb_command"):
        raise ServiceValidationError("Android TV ADB service is unavailable")
    response = await hass.services.async_call(
        "androidtv", "adb_command", {"entity_id": entity_id, "command": command},
        blocking=True, return_response=True, context=context,
    )
    if not isinstance(response, dict):
        raise HomeAssistantError("Android TV ADB returned no command response")
    result = response.get(entity_id, response)
    if not isinstance(result, dict) or not isinstance(result.get("adb_response"), str):
        raise HomeAssistantError("Android TV ADB returned no command response")
    return result["adb_response"]


async def async_adb_keys(hass, entity_id: str, context, *keys: str) -> None:
    """Send fixed ADB key commands and require acknowledgment from the shell."""
    command = " && sleep 0.15 && ".join(f"input keyevent KEYCODE_{key}" for key in keys)
    output = await async_adb_output(hass, entity_id, f"{command} && printf 'ok\\n'", context)
    if output.strip() != "ok":
        raise HomeAssistantError("Android TV did not accept the requested key input")


def normalize_input_name(value: str) -> str:
    """Map standard input labels and the names heard by Assist to stable names."""
    name = " ".join(value.casefold().split())
    hdmi = re.fullmatch(r"hdmi[ -]*([1-9][0-9]*)(?:\s*\([^)]*\))?", name)
    if hdmi:
        return f"HDMI {hdmi[1]}"
    if name in {"tv", "live tv", "antenna", "antenna tv", "방송", "지상파", "안테나", "tv 방송"}:
        return "TV"
    if name in {"av", "composite", "av input"}:
        return "AV"
    return ""


def tv_inputs(output: str) -> dict[str, set[str]]:
    """Associate selectable tuner, composite, and HDMI ports with TV input IDs."""
    hardware_map = re.search(r"(?m)^ +mHardwareInputIdMap:.*\n((?:^ +\d+:[^\n]+\n?)*)", output)
    if not hardware_map:
        return {}
    input_ids = dict(re.findall(r"(?m)^ +(\d+):[ \t]+(\S+)", hardware_map[1]))
    inputs: dict[str, set[str]] = {}
    for info in re.finditer(r"TvInputHardwareInfo\s*\{id=(\d+),\s*type=(\d+)([^}]*)}", output):
        input_id = input_ids.get(info[1])
        if not input_id:
            continue
        label = {"2": "TV", "3": "AV"}.get(info[2])
        if info[2] == "9":
            port = re.search(r"\bhdmi_port=([1-9][0-9]*)", info[3])
            label = f"HDMI {port[1]}" if port else None
        if label:
            inputs.setdefault(label, set()).add(input_id)
    return inputs


def active_input(output: str) -> str | None:
    """Get the input ID of the main TV session rather than a preview session."""
    main = re.search(r"(?m)^ +mainSessionToken:[ \t]+(\S+)", output)
    if not main or main[1] == "null":
        return None
    session = re.search(
        rf"(?m)^ +{re.escape(main[1])}: [^\n]*SessionState[^\n]*\n[ \t]+inputId:[ \t]+(\S+)",
        output,
    )
    return session[1] if session else None


def _row_input(row: ElementTree.Element) -> str:
    for node in row.iter():
        for attribute in ("text", "content-desc"):
            if label := normalize_input_name(node.get(attribute, "")):
                return label
    return ""


def _menu_position(output: str, target: str) -> tuple[str, int] | None:
    """Find the input row and the direction to reach it in the visible menu."""
    xml = re.search(r"<hierarchy\b.*?</hierarchy>", output, re.DOTALL)
    if not xml:
        return None
    try:
        root = ElementTree.fromstring(xml[0])
    except ElementTree.ParseError:
        return None
    focused = root.find(".//node[@focused='true']")
    for parent in root.iter("node"):
        rows = [row for row in parent if row.get("focusable") == "true" and row.get("enabled") == "true"]
        labels = [_row_input(row) for row in rows]
        if labels.count(target) != 1 or len(set(labels) - {""}) < 2:
            continue
        positions = [re.match(r"\[(\d+),(\d+)\]", row.get("bounds", "")) for row in rows]
        if not all(positions):
            continue
        horizontal = len({pos[2] for pos in positions}) == 1
        directions = ("LEFT", "RIGHT") if horizontal else ("UP", "DOWN")
        if focused is None or focused is parent:
            return directions[1], -1  # Enter D-pad focus after touch input.
        if focused not in rows:
            continue
        axis = 1 if horizontal else 2
        order = sorted(range(len(rows)), key=lambda index: int(positions[index][axis]))
        steps = order.index(labels.index(target)) - order.index(rows.index(focused))
        return directions[steps > 0], abs(steps)
    return None


async def async_switch_input(hass, entity_id: str, target: str, context) -> None:
    """Select a discovered input only after the source menu has focused its label."""
    output = await async_adb_output(hass, entity_id, TV_INPUT_DUMP, context)
    input_ids = tv_inputs(output).get(target)
    if not input_ids:
        raise ServiceValidationError("The requested TV input is not available")
    if active_input(output) in input_ids:
        return
    await async_adb_keys(hass, entity_id, context, "TV_INPUT")
    position = _menu_position(await async_adb_output(hass, entity_id, READ_INPUT_MENU, context), target)
    if position is not None and position[1] == -1:
        await async_adb_keys(hass, entity_id, context, f"DPAD_{position[0]}")
        position = _menu_position(await async_adb_output(hass, entity_id, READ_INPUT_MENU, context), target)
    if position is None or position[1] == -1:
        raise HomeAssistantError("The requested TV input could not be located in the input menu")
    direction, steps = position
    if steps:
        await async_adb_keys(hass, entity_id, context, *([f"DPAD_{direction}"] * steps))
        position = _menu_position(await async_adb_output(hass, entity_id, READ_INPUT_MENU, context), target)
        if position is None or position[1]:
            raise HomeAssistantError("The requested TV input could not be focused")
    await async_adb_keys(hass, entity_id, context, "DPAD_CENTER")
    for _ in range(5):
        output = await async_adb_output(hass, entity_id, TV_INPUT_DUMP, context)
        if active_input(output) in input_ids:
            return
        await asyncio.sleep(0.4)
    raise HomeAssistantError("The TV did not report the requested input as active")
