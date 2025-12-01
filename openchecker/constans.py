def _get_project_name(project_url):
    return f"""project_name=$(basename {project_url} | sed 's/\\\\.git$//') > /dev/null"""

def _clone_project(project_url, depth=False):
    depth_flag = "--depth=1" if depth else ""
    return f"""if [ ! -e "$project_name" ]; then
    GIT_ASKPASS=/bin/true git clone {depth_flag} {project_url} > /dev/null
fi"""

BASE_SCRIPT = _get_project_name("{project_url}") + "\n" + _clone_project("{project_url}")

download_checkout_shell_script = """
    """ + BASE_SCRIPT + """
    cd "$project_name"

    if [ {version_number} != "None" ]; then
        if git tag | grep -q "^{version_number}$"; then
            git checkout "{version_number}" && \\
            echo "成功切换到标签 {version_number}" || \\
            echo "切换到标签 {version_number} 失败"
        fi
    fi
    """

generate_lock_files_shell_script = """
    """ + BASE_SCRIPT + """
    if [ -e "$project_name/package.json" ] && [ ! -e "$project_name/package-lock.json" ]; then
        cd $project_name && npm install && rm -fr node_modules > /dev/null
        echo "Generate lock files for $project_name with command npm."
    fi
    if [ -e "$project_name/oh-package.json5" ] && [ ! -e "$project_name/oh-package-lock.json5" ]; then
        cd $project_name && ohpm install && rm -fr oh_modules > /dev/null
        echo "Generate lock files for $project_name with command ohpm."
    fi
    """

osv_scanner_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """

    if [ -f "$project_name/oh-package-lock.json5" ] && [ ! -f "$project_name/package-lock.json" ]; then
        mv $project_name/oh-package-lock.json5 $project_name/package-lock.json > /dev/null
        rename_flag=1
    fi

    osv-scanner --format json -r $project_name > $project_name/result.json
    cat $project_name/result.json

    if [ -v rename_flag ]; then
        mv $project_name/package-lock.json $project_name/oh-package-lock.json5 > /dev/null
    fi
    """

scancode_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    scancode -lc --json-pp scan_result.json $project_name --license-score 90 -n 4 > /dev/null
    cat scan_result.json
    rm -rf scan_result.json > /dev/null
    """

sonar_scanner_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    cd $project_name
    
    # 检测项目类型并进行相应配置
    echo "Detecting project type..."
    project_type="unknown"
    
    # 检查是否为Node.js/TypeScript项目
    if [ -f "package.json" ]; then
        echo "Detected Node.js/TypeScript project"
        project_type="nodejs"
        
        # 检查Node.js环境
        if command -v node &> /dev/null; then
            echo "Node.js version: $(node -v)"
        else
            echo "ERROR: Node.js not found! TypeScript analysis requires Node.js"
            echo "Please ensure Node.js is installed in the container"
            exit 1
        fi
        
        # 检查npm环境
        if command -v npm &> /dev/null; then
            echo "npm version: $(npm -v)"
        else
            echo "ERROR: npm not found! TypeScript analysis requires npm"
            exit 1
        fi
        
        # 检查TypeScript编译器
        if command -v tsc &> /dev/null; then
            echo "TypeScript compiler version: $(tsc -v)"
        else
            echo "WARNING: TypeScript compiler not found, installing..."
            npm install -g typescript || echo "Failed to install TypeScript globally"
        fi
        
        # 安装项目依赖（包含开发依赖，因为可能需要TypeScript等）
        if [ -f "package.json" ]; then
            echo "Installing project dependencies (including dev dependencies)..."
            npm install --silent || echo "Warning: npm install failed, continuing..."
            
            # 如果有package-lock.json，使用npm ci
            if [ -f "package-lock.json" ]; then
                echo "Found package-lock.json, using npm ci..."
                npm ci --silent || echo "Warning: npm ci failed, falling back to npm install"
            fi
        fi
        
        # 检查TypeScript配置文件
        if [ -f "tsconfig.json" ]; then
            echo "TypeScript configuration found: tsconfig.json"
            # 验证TypeScript配置
            if command -v tsc &> /dev/null; then
                echo "Validating TypeScript configuration..."
                tsc --noEmit --skipLibCheck > /dev/null 2>&1 || echo "Warning: TypeScript validation failed, continuing..."
            fi
        else
            echo "No tsconfig.json found, creating basic TypeScript configuration..."
            # 创建基本的TypeScript配置文件
            cat > tsconfig.json << 'TSCONFIG_EOF'
{{
  "compilerOptions": {{
    "target": "ES2020",
    "module": "commonjs",
    "allowJs": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "strict": false,
    "moduleResolution": "node",
    "noEmit": true
  }},
  "include": ["src/**/*", "lib/**/*", "app/**/*", "*.ts", "*.js"],
  "exclude": ["node_modules", "dist", "build"]
}}
TSCONFIG_EOF
            echo "Created basic tsconfig.json"
        fi
        
        # 检查是否有TypeScript文件
        ts_files=$(find . -name "*.ts" -o -name "*.tsx" | head -5)
        if [ -n "$ts_files" ]; then
            echo "Found TypeScript files:"
            echo "$ts_files"
        else
            echo "No TypeScript files found, but treating as JavaScript project"
        fi
    fi
    
    # 检查是否为Java项目
    if [ -f "pom.xml" ] || [ -f "build.gradle" ] || [ -f "build.gradle.kts" ]; then
        echo "Detected Java project"
        project_type="java"
    fi
    
    # 检查是否为Python项目
    if [ -f "requirements.txt" ] || [ -f "setup.py" ] || [ -f "pyproject.toml" ] || [ -f "Pipfile" ]; then
        echo "Detected Python project"
        project_type="python"
    fi
    
    # 检查是否为Go项目
    if [ -f "go.mod" ] || [ -f "go.sum" ]; then
        echo "Detected Go project"
        project_type="go"
    fi
    
    # 检查是否为C#项目
    if [ -f "*.csproj" ] || [ -f "*.sln" ] || [ -f "project.json" ]; then
        echo "Detected C# project"
        project_type="csharp"
    fi
    
    # 检查是否为PHP项目
    if [ -f "composer.json" ] || [ -f "composer.lock" ]; then
        echo "Detected PHP project"
        project_type="php"
    fi
    
    # 动态创建或更新sonar-project.properties文件
    echo "Configuring SonarQube properties..."
    cat > sonar-project.properties << EOF
# 项目基本信息
sonar.projectKey={sonar_project_name}
sonar.projectName={sonar_project_name}
sonar.projectVersion=1.0.0
sonar.sourceEncoding=UTF-8

# 根据项目类型配置源代码路径
EOF
    
    # 根据项目类型添加特定配置
    case "$project_type" in
        "nodejs")
            # 动态检测源代码目录
            source_dirs=""
            
            # 检查常见的源代码目录
            for dir in src lib app components pages utils client server; do
                if [ -d "$dir" ]; then
                    if [ -z "$source_dirs" ]; then
                        source_dirs="$dir"
                    else
                        source_dirs="$source_dirs,$dir"
                    fi
                    echo "发现源代码目录: $dir"
                fi
            done
            
            # 检查根目录下的TypeScript/JavaScript文件
            root_files=$(find . -maxdepth 1 -name "*.ts" -o -name "*.js" -o -name "*.tsx" -o -name "*.jsx" | grep -v node_modules | head -10)
            if [ -n "$root_files" ]; then
                if [ -z "$source_dirs" ]; then
                    source_dirs="."
                else
                    source_dirs="$source_dirs,."
                fi
                echo "发现根目录源文件: $(echo $root_files | tr '\n' ' ')"
            fi
            
            # 如果仍然没有找到，使用当前目录作为默认值
            if [ -z "$source_dirs" ]; then
                source_dirs="."
                echo "未找到标准源代码目录，使用当前目录"
            else
                # 如果source_dirs包含src和.，只保留src避免重复索引
                if [[ "$source_dirs" == *"src"* && "$source_dirs" == *"."* ]]; then
                    source_dirs="src"
                    echo "检测到src目录和根目录重复，只使用src目录"
                fi
            fi
            
            echo "Detected source directories: $source_dirs"
            
            cat >> sonar-project.properties << EOF
# Node.js/TypeScript项目配置
sonar.sources=$source_dirs
sonar.tests=test
sonar.exclusions=**/node_modules/**,**/dist/**,**/build/**,**/coverage/**,**/*.min.js,**/*.bundle.js,**/*.d.ts,**/public/**,**/static/**,**/.next/**,**/.nuxt/**,**/vendor/**

# 测试文件排除
sonar.test.exclusions=**/*.test.ts,**/*.test.js,**/*.spec.ts,**/*.spec.js,**/*.test.tsx,**/*.spec.tsx

# TypeScript特定配置
sonar.typescript.node.maxspace={typescript_node_maxspace}
sonar.typescript.lcov.reportPaths=coverage/lcov.info,coverage/lcov-report/lcov.info
sonar.javascript.lcov.reportPaths=coverage/lcov.info,coverage/lcov-report/lcov.info

# ESLint配置
sonar.eslint.reportPaths=eslint-report.json,reports/eslint-report.json

# 测试覆盖率配置
sonar.coverage.exclusions=**/*.test.ts,**/*.test.js,**/*.spec.ts,**/*.spec.js,**/*.test.tsx,**/*.spec.tsx,**/node_modules/**,**/coverage/**,**/*.config.js,**/*.config.ts

# 文件后缀配置 - 确保TypeScript文件被识别
sonar.javascript.file.suffixes=.js,.jsx,.mjs,.cjs
sonar.typescript.file.suffixes=.ts,.tsx,.mts,.cts

# 强制启用JavaScript/TypeScript分析
sonar.javascript.environments=node,browser,jest,mocha
sonar.typescript.tsconfigPath=tsconfig.json

# 强制启用TypeScript分析器
sonar.typescript.ignoreHeaderComments=false
sonar.typescript.exclusions=**/node_modules/**,**/dist/**,**/build/**

# 确保SonarJS插件处理TypeScript文件
sonar.sources.inclusions=**/*.ts,**/*.tsx,**/*.js,**/*.jsx

# 日志配置 - 使用DEBUG获取更多信息
sonar.log.level=DEBUG
EOF
            ;;
        "java")
            cat >> sonar-project.properties << EOF
# Java项目配置
sonar.sources=src/main/java,src/main/kotlin,src
sonar.tests=src/test/java,src/test/kotlin,test
sonar.java.binaries=target/classes,build/classes/java/main,build/classes/kotlin/main
sonar.java.test.binaries=target/test-classes,build/classes/java/test,build/classes/kotlin/test
sonar.java.libraries=target/dependency/*.jar,build/libs/*.jar
sonar.exclusions=**/target/**,**/build/**,**/*.class,**/generated-sources/**
sonar.coverage.jacoco.xmlReportPaths=target/site/jacoco/jacoco.xml,build/reports/jacoco/test/jacocoTestReport.xml
EOF
            ;;
        "python")
            cat >> sonar-project.properties << EOF
# Python项目配置
sonar.sources=src,lib,app,.
sonar.tests=tests,test
sonar.exclusions=**/venv/**,**/env/**,**/.venv/**,**/__pycache__/**,**/build/**,**/dist/**,**/*.pyc,**/migrations/**,**/settings/**
sonar.test.exclusions=**/test_*.py,**/*_test.py,**/conftest.py
sonar.python.coverage.reportPaths=coverage.xml,htmlcov/coverage.xml
sonar.python.xunit.reportPath=test-reports/junit.xml
# Python版本配置
sonar.python.version=3.8,3.9,3.10,3.11,3.12
EOF
            ;;
        "go")
            cat >> sonar-project.properties << EOF
# Go项目配置
sonar.sources=.
sonar.tests=.
sonar.exclusions=**/vendor/**,**/testdata/**,**/*_test.go
sonar.test.inclusions=**/*_test.go
sonar.go.coverage.reportPaths=coverage.out,cover.out
EOF
            ;;
        "csharp")
            cat >> sonar-project.properties << EOF
# C#项目配置
sonar.sources=.
sonar.exclusions=**/bin/**,**/obj/**,**/packages/**,**/TestResults/**,**/*.Tests/**
sonar.cs.dotcover.reportsPaths=dotCover.html
sonar.cs.opencover.reportsPaths=coverage.xml
sonar.cs.nunit.reportsPaths=TestResult.xml
EOF
            ;;
        "php")
            cat >> sonar-project.properties << EOF
# PHP项目配置
sonar.sources=src,lib,app
sonar.tests=tests,test
sonar.exclusions=**/vendor/**,**/cache/**,**/storage/**,**/bootstrap/cache/**
sonar.php.coverage.reportPaths=coverage.xml,clover.xml
sonar.php.tests.reportPath=phpunit.xml
EOF
            ;;
        *)
            cat >> sonar-project.properties << EOF
# 通用项目配置
sonar.sources=src,lib,app,.
sonar.exclusions=**/node_modules/**,**/venv/**,**/env/**,**/__pycache__/**,**/build/**,**/dist/**,**/target/**,**/vendor/**,**/bin/**,**/obj/**
EOF
            ;;
    esac
    
    # 构建SonarQube服务器URL
    if [[ "{sonar_host}" =~ ^https?:// ]]; then
        sonar_url="{sonar_host}"
    else
        # 检查是否为IP地址
        if [[ "{sonar_host}" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$ ]]; then
            # It's an IP address, use http protocol and add port
            if [ -n "{sonar_port}" ] && [ "{sonar_port}" != "None" ]; then
                sonar_url="http://{sonar_host}:{sonar_port}"
            else
                sonar_url="http://{sonar_host}"
            fi
        else
            # It's a domain name, use https protocol
            sonar_url="https://{sonar_host}"
        fi
    fi
    
    echo "Starting SonarQube analysis..."
    echo "SonarQube URL: $sonar_url"
    echo "Project Key: {sonar_project_name}"
    echo "Project Type: $project_type"
    
    # 显示当前目录内容
    echo "Current directory contents:"
    ls -la
    
    # 显示sonar-project.properties内容
    echo "=== sonar-project.properties ==="
    cat sonar-project.properties
    echo "================================"
    
    # 检查sonar-scanner版本
    echo "SonarScanner version:"
    sonar-scanner --version || echo "Failed to get sonar-scanner version"
    
    # 执行SonarQube扫描前的最终检查
    echo "=== 扫描前环境检查 ==="
    echo "工作目录: $(pwd)"
    echo "项目类型: $project_type"
    echo "SonarQube URL: $sonar_url"
    echo "项目Key: {sonar_project_name}"
    
    # 检查关键文件是否存在
    if [ -f "sonar-project.properties" ]; then
        echo "✅ sonar-project.properties 存在"
        echo "文件大小: $(wc -l < sonar-project.properties) 行"
    else
        echo "❌ sonar-project.properties 不存在"
        exit 1
    fi
    
    if [ "$project_type" = "nodejs" ]; then
        if [ -f "tsconfig.json" ]; then
            echo "✅ tsconfig.json 存在"
        else
            echo "⚠️  tsconfig.json 不存在"
        fi
        
        if [ -f "package.json" ]; then
            echo "✅ package.json 存在"
        else
            echo "❌ package.json 不存在"
        fi
        
        # 检查源代码文件
        ts_count=$(find . -name "*.ts" -not -path "./node_modules/*" | wc -l)
        js_count=$(find . -name "*.js" -not -path "./node_modules/*" | wc -l)
        echo "TypeScript文件数量: $ts_count"
        echo "JavaScript文件数量: $js_count"
        
        if [ $ts_count -eq 0 ] && [ $js_count -eq 0 ]; then
            echo "⚠️  未找到TypeScript或JavaScript源文件"
        fi
    fi
    
    echo "=== 开始SonarQube扫描 ==="
    echo "Executing SonarQube scan..."
    # 设置扫描超时（秒）
    timeout {scan_timeout} sonar-scanner \\
        -Dsonar.host.url=$sonar_url \\
        -Dsonar.token={sonar_token} \\
        -Dsonar.log.level=DEBUG \\
        -Dsonar.verbose=true \\
        -Dsonar.scanner.socketTimeout=300 \\
        -Dsonar.scanner.responseTimeout=300
        
    scan_result=$?
    echo "=== SonarQube扫描结果 ==="
    echo "扫描退出代码: $scan_result"
    
    if [ $scan_result -eq 0 ]; then
        echo "✅ SonarQube扫描成功完成"
        echo "项目: {sonar_project_name}"
        echo "类型: $project_type"
    elif [ $scan_result -eq 124 ]; then
        echo "⏰ SonarQube扫描超时 ({scan_timeout}秒)"
        echo "建议: 增加scan_timeout配置或检查网络连接"
    else
        echo "❌ SonarQube扫描失败，退出代码: $scan_result"
        echo "项目类型: $project_type"
        echo "配置文件内容:"
        echo "--- sonar-project.properties ---"
        cat sonar-project.properties || echo "无法读取配置文件"
        echo "--- 环境信息 ---"
        echo "Node.js: $(node -v 2>/dev/null || echo '未安装')"
        echo "npm: $(npm -v 2>/dev/null || echo '未安装')"
        echo "TypeScript: $(tsc -v 2>/dev/null || echo '未安装')"
        echo "SonarScanner: $(sonar-scanner --version 2>/dev/null | head -1 || echo '未安装')"
    fi
    
    cd ..
    """

dependency_checker_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    ort -P ort.analyzer.allowDynamicVersions=true analyze -i $project_name -o $project_name -f JSON > /dev/null
    cat $project_name/analyzer-result.json
    """

readme_checker_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    find "$project_name" -type f \\( -name "README*" -o -name "docs/README*" \\) -print
    """

maintainers_checker_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    find "$project_name" -type f \\( -iname "MAINTAINERS*" -o -iname "COMMITTERS*" -o -iname "OWNERS*" -o -iname "CODEOWNERS*" \\) -print
    """

languages_detector_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    github-linguist $project_name --breakdown --json
    """

oat_scanner_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """                
    if [ ! -f "$project_name/OAT.xml" ]; then
        echo "OAT.xml not found in the project root directory."
        exit 1   
    fi
    java -jar ohos_ossaudittool-2.0.0.jar -mode s -s $project_name -r $project_name/oat_out -n $project_name > /dev/null            
    report_file="$project_name/oat_out/single/PlainReport_$project_name.txt"
    [ -f "$report_file" ] && cat "$report_file"                        
    """

remove_source_code_shell_script = """
    """ + _get_project_name("{project_url}") + """
    if [ -e "$project_name" ]; then
        rm -rf $project_name > /dev/null
    fi
    """

license_detector_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    licensee detect "$project_name" --json
    rm -rf $project_name > /dev/null
    """

shell_script_handlers = {
    "download-checkout": download_checkout_shell_script,
    "generate-lock_files": generate_lock_files_shell_script,
    "osv-scanner": osv_scanner_shell_script,
    "scancode": scancode_shell_script,
    "sonar-scanner": sonar_scanner_shell_script,
    "dependency-checker": dependency_checker_shell_script,
    "readme-checker": readme_checker_shell_script,
    "maintainers-checker": maintainers_checker_shell_script,
    "languages-detector": languages_detector_shell_script,
    "oat-scanner": oat_scanner_shell_script,
    "remove-source-code": remove_source_code_shell_script,
    "license-detector": license_detector_shell_script,
}