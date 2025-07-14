#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志分析工具
用于分析openchecker的日志文件，提供统计信息
"""

import json
import re
import os
import argparse
from datetime import datetime
from collections import Counter
from typing import Dict, List, Any, Optional

class LogAnalyzer:
    """日志分析器"""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.logs = []
        self.stats = {}
    
    def load_logs(self) -> None:
        """加载日志文件"""
        if not os.path.exists(self.log_file):
            print(f"日志文件不存在: {self.log_file}")
            return
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    # 尝试解析JSON格式的结构化日志
                    log_entry = json.loads(line)
                    self.logs.append(log_entry)
                except json.JSONDecodeError:
                    # 如果不是JSON格式，尝试解析简单格式
                    log_entry = self._parse_simple_log(line)
                    if log_entry:
                        self.logs.append(log_entry)
    
    def _parse_simple_log(self, line: str) -> Optional[Dict[str, Any]]:
        """解析简单格式的日志"""
        # 匹配格式: 2024-01-01 12:00:00 [INFO] module:123: message
        pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (\w+):(\d+): (.+)'
        match = re.match(pattern, line)
        
        if match:
            timestamp, level, module, line_num, message = match.groups()
            return {
                'timestamp': timestamp,
                'level': level,
                'logger': module,
                'line': int(line_num),
                'message': message
            }
        return None
    
    def analyze_logs(self) -> Dict[str, Any]:
        """分析日志"""
        if not self.logs:
            print("没有找到有效的日志条目")
            return {}
        
        stats = {
            'total_logs': len(self.logs),
            'time_range': self._get_time_range(),
            'level_distribution': self._get_level_distribution(),
            'module_distribution': self._get_module_distribution(),
            'error_analysis': self._get_error_analysis()
        }
        
        self.stats = stats
        return stats
    
    def _get_time_range(self) -> Dict[str, str]:
        """获取时间范围"""
        timestamps = []
        for log in self.logs:
            if 'timestamp' in log:
                try:
                    if isinstance(log['timestamp'], str):
                        # 处理ISO格式时间戳
                        if 'T' in log['timestamp']:
                            dt = datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00'))
                        else:
                            dt = datetime.strptime(log['timestamp'], '%Y-%m-%d %H:%M:%S')
                        timestamps.append(dt)
                except:
                    continue
        
        if timestamps:
            return {
                'start': min(timestamps).isoformat(),
                'end': max(timestamps).isoformat(),
                'duration_hours': (max(timestamps) - min(timestamps)).total_seconds() / 3600
            }
        return {}
    
    def _get_level_distribution(self) -> Dict[str, int]:
        """获取日志级别分布"""
        levels = [log.get('level', 'UNKNOWN') for log in self.logs]
        return dict(Counter(levels))
    
    def _get_module_distribution(self) -> Dict[str, int]:
        """获取模块分布"""
        modules = [log.get('logger', 'unknown') for log in self.logs]
        return dict(Counter(modules))
    
    def _get_error_analysis(self) -> Dict[str, Any]:
        """错误分析"""
        errors = [log for log in self.logs if log.get('level') == 'ERROR']
        
        error_messages = []
        for error in errors:
            message = error.get('message', '')
            if 'exception' in error:
                error_messages.append(error['exception'].get('message', message))
            else:
                error_messages.append(message)
        
        return {
            'total_errors': len(errors),
            'error_rate': len(errors) / len(self.logs) if self.logs else 0,
            'top_errors': dict(Counter(error_messages).most_common(10))
        }
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """生成分析报告"""
        if not self.stats:
            self.analyze_logs()
        
        report = []
        report.append("=" * 60)
        report.append("OpenChecker 日志分析报告")
        report.append("=" * 60)
        report.append(f"分析时间: {datetime.now().isoformat()}")
        report.append(f"日志文件: {self.log_file}")
        report.append("")
        
        # 基本统计
        report.append("基本统计:")
        report.append(f"  总日志条数: {self.stats.get('total_logs', 0)}")
        if 'time_range' in self.stats and self.stats['time_range']:
            tr = self.stats['time_range']
            report.append(f"  时间范围: {tr.get('start', 'N/A')} 到 {tr.get('end', 'N/A')}")
            report.append(f"  持续时间: {tr.get('duration_hours', 0):.2f} 小时")
        report.append("")
        
        # 日志级别分布
        report.append("日志级别分布:")
        for level, count in self.stats.get('level_distribution', {}).items():
            percentage = (count / self.stats['total_logs']) * 100
            report.append(f"  {level}: {count} ({percentage:.1f}%)")
        report.append("")
        
        # 模块分布
        report.append("模块分布:")
        for module, count in self.stats.get('module_distribution', {}).items():
            percentage = (count / self.stats['total_logs']) * 100
            report.append(f"  {module}: {count} ({percentage:.1f}%)")
        report.append("")
        
        # 错误分析
        error_analysis = self.stats.get('error_analysis', {})
        if error_analysis:
            report.append("错误分析:")
            report.append(f"  总错误数: {error_analysis.get('total_errors', 0)}")
            report.append(f"  错误率: {error_analysis.get('error_rate', 0):.2%}")
            report.append("  常见错误:")
            for error, count in error_analysis.get('top_errors', {}).items():
                report.append(f"    {error}: {count} 次")
            report.append("")
        
        report_text = "\n".join(report)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            print(f"报告已保存到: {output_file}")
        
        return report_text

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='OpenChecker 日志分析工具')
    parser.add_argument('log_file', help='日志文件路径')
    parser.add_argument('--output', '-o', help='输出报告文件路径')
    
    args = parser.parse_args()
    
    analyzer = LogAnalyzer(args.log_file)
    analyzer.load_logs()
    
    if analyzer.logs:
        print(f"加载了 {len(analyzer.logs)} 条日志记录")
        analyzer.generate_report(args.output)
    else:
        print("没有找到有效的日志记录")

if __name__ == '__main__':
    main() 