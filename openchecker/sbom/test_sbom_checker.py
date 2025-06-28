#!/usr/bin/env python3
"""
测试 SBOM 检查器
"""

import os
import sys
import tempfile
import shutil

from sbom_checker import check_sbom_for_project

def test_sbom_checker():
    """测试 SBOM 检查器"""
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建测试项目目录
        test_project = os.path.join(temp_dir, "test-project")
        os.makedirs(test_project)
        
        # 创建一些测试文件
        test_files = [
            "README.md",
            "package.json",
            "test-sbom.spdx.json",
            "another-sbom.cdx.json",
            "not-sbom.txt"
        ]
        
        for file_name in test_files:
            with open(os.path.join(test_project, file_name), 'w') as f:
                f.write(f"Test content for {file_name}")
        
        # 切换到临时目录
        original_dir = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            # 测试 SBOM 检查
            result = check_sbom_for_project("https://github.com/test/test-project.git")
            
            print("SBOM 检查结果:")
            print(f"状态: {result.get('status')}")
            print(f"分数: {result.get('score')}")
            print(f"有 SBOM 文件: {result.get('has_sbom')}")
            print(f"有发布 SBOM: {result.get('has_release_sbom')}")
            print(f"SBOM 文件列表: {result.get('sbom_files')}")
            
            if result.get("error"):
                print(f"错误: {result.get('error')}")
                
        finally:
            # 恢复原始目录
            os.chdir(original_dir)


if __name__ == "__main__":
    test_sbom_checker() 
