DATA 볼륨에 대한 폴더 경로의 목록입니다.
볼륨 일련 번호가 00000162 C2CC:C1F2입니다.
D:\HA\HACS\YOUTUBE_CONTENT_SEARCH-MAIN
│  changelog.jsonl
│  hacs.json
│  icon.png
│  info.md
│  LICENSE
│  logo.png
│  README.md
│  temp_test_file.py
│  test_awaited_case.py
│  test_collect.py
│  test_detect.py
│  test_panel_api.py
│  test_unawaited.py
│  test_unawaited_case.py
│  tree.md
│  validate_syntax.py
│  
├─custom_components
│  ├─private_hacs
│  │  │  config_flow.py
│  │  │  const.py
│  │  │  coordinator.py
│  │  │  github.py
│  │  │  helpers.py
│  │  │  manifest.json
│  │  │  panel.py
│  │  │  services.py
│  │  │  services.yaml
│  │  │  store.py
│  │  │  strings.json
│  │  │  update.py
│  │  │  __init__.py
│  │  │  
│  │  ├─brand
│  │  │      icon.png
│  │  │      
│  │  ├─frontend
│  │  │  │  panel.html
│  │  │  │  
│  │  │  └─js
│  │  │          marked.min.js
│  │  │          panel.js
│  │  │          
│  │  ├─translations
│  │  │      ko.json
│  │  │      
│  │  └─__pycache__
│  │          config_flow.cpython-314.pyc
│  │          const.cpython-314.pyc
│  │          coordinator.cpython-314.pyc
│  │          github.cpython-314.pyc
│  │          helpers.cpython-314.pyc
│  │          panel.cpython-314.pyc
│  │          services.cpython-314.pyc
│  │          store.cpython-314.pyc
│  │          update.cpython-314.pyc
│  │          __init__.cpython-314.pyc
│  │          
│  └─youtube_content_search
│      │  config_flow.py
│      │  const.py
│      │  manifest.json
│      │  options_flow.py
│      │  services.py
│      │  services.yaml
│      │  __init__.py
│      │  
│      └─frontend
│              panel.html
│              panel.js
│              styles.css
│              
├─servers
│  │  .gitattributes
│  │  .gitignore
│  │  .mcp.json
│  │  .npmrc
│  │  ADDITIONAL.md
│  │  CLAUDE.md
│  │  CODE_OF_CONDUCT.md
│  │  CONTRIBUTING.md
│  │  LICENSE
│  │  package-lock.json
│  │  package.json
│  │  README.md
│  │  RELEASING.md
│  │  SECURITY.md
│  │  tsconfig.json
│  │  
│  ├─.github
│  │  │  pull_request_template.md
│  │  │  
│  │  └─workflows
│  │          claude.yml
│  │          python.yml
│  │          readme-pr-check.yml
│  │          release.yml
│  │          typescript.yml
│  │          
│  ├─scripts
│  │      release.py
│  │      
│  └─src
│      ├─everything
│      │  │  .prettierignore
│      │  │  AGENTS.md
│      │  │  Dockerfile
│      │  │  index.ts
│      │  │  package.json
│      │  │  README.md
│      │  │  tsconfig.json
│      │  │  vitest.config.ts
│      │  │  
│      │  ├─docs
│      │  │      architecture.md
│      │  │      extension.md
│      │  │      features.md
│      │  │      how-it-works.md
│      │  │      instructions.md
│      │  │      startup.md
│      │  │      structure.md
│      │  │      
│      │  ├─prompts
│      │  │      args.ts
│      │  │      completions.ts
│      │  │      index.ts
│      │  │      resource.ts
│      │  │      simple.ts
│      │  │      
│      │  ├─resources
│      │  │      files.ts
│      │  │      index.ts
│      │  │      session.ts
│      │  │      subscriptions.ts
│      │  │      templates.ts
│      │  │      
│      │  ├─server
│      │  │      index.ts
│      │  │      logging.ts
│      │  │      roots.ts
│      │  │      
│      │  ├─tools
│      │  │      echo.ts
│      │  │      get-annotated-message.ts
│      │  │      get-env.ts
│      │  │      get-resource-links.ts
│      │  │      get-resource-reference.ts
│      │  │      get-roots-list.ts
│      │  │      get-structured-content.ts
│      │  │      get-sum.ts
│      │  │      get-tiny-image.ts
│      │  │      gzip-file-as-resource.ts
│      │  │      index.ts
│      │  │      simulate-research-query.ts
│      │  │      toggle-simulated-logging.ts
│      │  │      toggle-subscriber-updates.ts
│      │  │      trigger-elicitation-request-async.ts
│      │  │      trigger-elicitation-request.ts
│      │  │      trigger-long-running-operation.ts
│      │  │      trigger-sampling-request-async.ts
│      │  │      trigger-sampling-request.ts
│      │  │      trigger-url-elicitation.ts
│      │  │      
│      │  ├─transports
│      │  │      sse.ts
│      │  │      stdio.ts
│      │  │      streamableHttp.ts
│      │  │      
│      │  └─__tests__
│      │          prompts.test.ts
│      │          registrations.test.ts
│      │          resources.test.ts
│      │          server.test.ts
│      │          tools.test.ts
│      │          
│      ├─fetch
│      │  │  .python-version
│      │  │  Dockerfile
│      │  │  LICENSE
│      │  │  pyproject.toml
│      │  │  README.md
│      │  │  uv.lock
│      │  │  
│      │  ├─src
│      │  │  └─mcp_server_fetch
│      │  │          server.py
│      │  │          __init__.py
│      │  │          __main__.py
│      │  │          
│      │  └─tests
│      │          test_server.py
│      │          __init__.py
│      │          
│      ├─filesystem
│      │  │  Dockerfile
│      │  │  index.ts
│      │  │  lib.ts
│      │  │  package.json
│      │  │  path-utils.ts
│      │  │  path-validation.ts
│      │  │  README.md
│      │  │  roots-utils.ts
│      │  │  tsconfig.json
│      │  │  vitest.config.ts
│      │  │  
│      │  └─__tests__
│      │          directory-tree.test.ts
│      │          lib.test.ts
│      │          path-utils.test.ts
│      │          path-validation.test.ts
│      │          roots-utils.test.ts
│      │          startup-validation.test.ts
│      │          structured-content.test.ts
│      │          
│      ├─git
│      │  │  .gitignore
│      │  │  .python-version
│      │  │  Dockerfile
│      │  │  LICENSE
│      │  │  pyproject.toml
│      │  │  README.md
│      │  │  uv.lock
│      │  │  
│      │  ├─src
│      │  │  └─mcp_server_git
│      │  │          py.typed
│      │  │          server.py
│      │  │          __init__.py
│      │  │          __main__.py
│      │  │          
│      │  └─tests
│      │          test_server.py
│      │          
│      ├─memory
│      │  │  Dockerfile
│      │  │  index.ts
│      │  │  package.json
│      │  │  README.md
│      │  │  tsconfig.json
│      │  │  vitest.config.ts
│      │  │  
│      │  └─__tests__
│      │          file-path.test.ts
│      │          knowledge-graph.test.ts
│      │          resource.test.ts
│      │          
│      ├─sequentialthinking
│      │  │  Dockerfile
│      │  │  index.ts
│      │  │  lib.ts
│      │  │  package.json
│      │  │  README.md
│      │  │  tsconfig.json
│      │  │  vitest.config.ts
│      │  │  
│      │  └─__tests__
│      │          lib.test.ts
│      │          
│      └─time
│          │  .python-version
│          │  Dockerfile
│          │  pyproject.toml
│          │  README.md
│          │  uv.lock
│          │  
│          ├─src
│          │  └─mcp_server_time
│          │          server.py
│          │          __init__.py
│          │          __main__.py
│          │          
│          └─test
│                  time_server_test.py
│                  
└─youtube_content_search_backup
        config_flow.py
        const.py
        manifest.json
        services.py
        services.yaml
        __init__.py
        
