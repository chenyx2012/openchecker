

download_checkout_shell_script = """
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    GIT_ASKPASS=/bin/true git clone {project_url}
                fi

                cd "$project_name"

                if [ {version_number} != "None" ]; then
                    # 检查版本号是否在git仓库的tag中
                    if git tag | grep -q "^$version_number$"; then
                        # 切换到对应的tag
                        git checkout "$version_number"
                        if [ $? -eq 0 ]; then
                            echo "成功切换到标签 $version_number"
                        else
                            echo "切换到标签 $version_number 失败"
                        fi
                    fi
                fi
            """

generate_lock_files_shell_script = shell_script="""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ -e "$project_name/package.json" ] && [ ! -e "$project_name/package-lock.json" ]; then
                    cd $project_name && npm install && rm -fr node_modules > /dev/null
                    echo "Generate lock files for $project_name with command npm."
                fi
                if [ -e "$project_name/oh-package.json5" ] && [ ! -e "$project_name/oh-package-lock.json5" ]; then
                    cd $project_name && ohpm install && rm -fr oh_modules > /dev/null
                    echo "Generate lock files for $project_name with command ohpm."
                fi
            """

# When osv-scanner tool specify the '--format json' option, only the scan results are output to the standard output.
            # All other information is redirected to the standard error output;
            # Hence, error values are not checked here.
osv_scanner_shell_script = """
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    GIT_ASKPASS=/bin/true git clone --depth=1 {project_url} > /dev/null
                fi

                # Rename oh-package-lock.json5 to package-lock.json make it readable by osv-scanner.
                if [ -f "$project_name/oh-package-lock.json5" ] && [! -f "$project_name/package-lock.json" ]; then
                    mv $project_name/oh-package-lock.json5 $project_name/package-lock.json  > /dev/null
                    rename_flag = 1
                fi

                # Outputs the results as a JSON object to stdout, with all other output being directed to stderr
                # - this makes it safe to redirect the output to a file.
                # shell_exec function return (None, error) when process.returncode is not 0, so we redirect output to a file and cat.
                osv-scanner --format json -r $project_name > $project_name/result.json
                cat $project_name/result.json
                # rm -rf $project_name > /dev/null

                if [ -v rename_flag ]; then
                    mv $project_name/package-lock.json $project_name/oh-package-lock.json5  > /dev/null
                fi
            """

scancode_shell_script = """
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    GIT_ASKPASS=/bin/true git clone --depth=1 {project_url} > /dev/null
                fi
                scancode -lc --json-pp scan_result.json $project_name --license-score 90 -n 4 > /dev/null
                cat scan_result.json
                rm -rf scan_result.json > /dev/null
                # rm -rf $project_name scan_result.json > /dev/null
            """

sonar_scanner_shell_script = shell_script="""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    GIT_ASKPASS=/bin/true git clone --depth=1 {project_url} > /dev/null
                fi
                cp -r $project_name ~/ && cd ~
                sonar-scanner \
                    -Dsonar.projectKey={sonar_project_name} \
                    -Dsonar.sources=$project_name \
                    -Dsonar.host.url=http://{sonar_config['host']}:{sonar_config['port']} \
                    -Dsonar.token={sonar_config['token']} \
                    -Dsonar.exclusions=**/*.java
                rm -rf $project_name > /dev/null
            """

dependency_checker_shell_script = shell_script="""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    GIT_ASKPASS=/bin/true git clone --depth=1 {project_url} > /dev/null
                fi
                ort -P ort.analyzer.allowDynamicVersions=true analyze -i $project_name -o $project_name -f JSON > /dev/null
                cat $project_name/analyzer-result.json
                # rm -rf $project_name > /dev/null
            """

readme_checker_shell_script = shell_script="""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    GIT_ASKPASS=/bin/true git clone --depth=1 {project_url} > /dev/null
                fi
                find "$project_name" -type f \( -name "README*" -o -name "docs/README*" \) -print
            """

maintainers_checker_shell_script = """
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    GIT_ASKPASS=/bin/true git clone --depth=1 {project_url} > /dev/null
                fi
                find "$project_name" -type f \( -iname "MAINTAINERS*" -o -iname "COMMITTERS*" -o -iname "OWNERS*" -o -iname "CODEOWNERS*" \) -print
            """

languages_detector_shell_script = """
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    GIT_ASKPASS=/bin/true git clone --depth=1 {project_url} > /dev/null
                fi
                github-linguist $project_name --breakdown --json
            """

oat_scanner_shell_script = """
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    GIT_ASKPASS=/bin/true git clone --depth=1 {project_url} > /dev/null
                fi                
                if [ ! -f "$project_name/OAT.xml" ]; then
                    echo "OAT.xml not found in the project root directory."
                    exit 1   
                fi
                java -jar ohos_ossaudittool-2.0.0.jar -mode s -s $project_name   -r $project_name/oat_out -n $project_name > /dev/null            
                report_file="$project_name/oat_out/single/PlainReport_$project_name.txt"
                if [ -f "$report_file" ]; then                    
                    cat "$report_file"                                    
                fi                        
            """

remove_source_code_shell_script = """
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ -e "$project_name" ]; then
                    rm -rf $project_name > /dev/null
                fi
            """

license_detector_shell_script = """
                    project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                    if [ ! -e "$project_name" ]; then
                        GIT_ASKPASS=/bin/true git clone --depth=1 {project_url} > /dev/null
                    fi
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