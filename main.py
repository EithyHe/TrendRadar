#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrendRadar - 多平台热点资讯监控分析系统（历史分析增强版）
作者：基于原项目改进
功能：支持历史数据汇总、趋势分析、多维度统计
"""

import requests
import json
import os
import re
import time
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import List, Dict, Any, Tuple
import html

# ====== 配置参数 ======
CONFIG = {
    "FEISHU_WEBHOOK_URL": os.environ.get("FEISHU_WEBHOOK_URL"),
    "HISTORY_DAYS": int(os.environ.get("HISTORY_DAYS", "1")),  # 从环境变量读取，默认1天
    "HISTORY_HOURS": int(os.environ.get("HISTORY_HOURS", "0")),  # 小时数，默认0
    "CUSTOM_START_DATE": os.environ.get("CUSTOM_START_DATE", ""),  # 自定义开始日期 YYYY-MM-DD
    "CUSTOM_END_DATE": os.environ.get("CUSTOM_END_DATE", ""),  # 自定义结束日期 YYYY-MM-DD
    "MAX_RESULTS_PER_PLATFORM": 50,  # 增加获取数量以支持历史分析
    "TOP_KEYWORDS_LIMIT": 20,  # 增加显示的关键词数量
    "TOP_NEWS_PER_KEYWORD": 8,  # 增加每个关键词显示的新闻数量
    "FEISHU_SHOW_VERSION_UPDATE": True,
    "CONTINUE_WITHOUT_FEISHU": True,  # 没有飞书配置也继续运行
    "API_BASE_URL": "https://newsnow.busiyi.world/api/news",  # 使用备用API地址
    "BACKUP_API_URLS": [  # 备用API列表
        "https://api.newsnow.cc/api/news",
        "https://newsnow.busiyi.world/api/news", 
        "https://newsnow.cc/api/news"
    ],
    "REQUEST_DELAY": 0.3,  # 减少请求间隔以提高效率
    "ENABLE_TREND_ANALYSIS": True,  # 启用趋势分析
}

# ====== 支持的平台配置 ======
PLATFORMS = [
    ("toutiao", "今日头条"),
    ("baidu", "百度热搜"), 
    ("weibo", "微博"),
    ("zhihu", "知乎"),
    ("douyin", "抖音"),
    ("bilibili-hot-search", "bilibili热搜"),
    ("wallstreetcn-hot", "华尔街见闻"),
    ("thepaper", "澎湃新闻"),
    ("cls-hot", "财联社热门"),
    ("ifeng", "凤凰网"),
    ("tieba", "贴吧"),
]

class TrendAnalyzer:
    def __init__(self):
        self.frequency_words = self.load_frequency_words()
        self.filter_words = self.load_filter_words()
        self.must_words = self.load_must_words()
        self.all_data = []
        self.analysis_result = {}
        self.time_range = self.calculate_time_range()
        
    def calculate_time_range(self) -> Dict[str, Any]:
        """计算分析的时间范围"""
        now = datetime.now()
        
        # 如果设置了自定义日期范围
        if CONFIG['CUSTOM_START_DATE'] and CONFIG['CUSTOM_END_DATE']:
            try:
                start_date = datetime.strptime(CONFIG['CUSTOM_START_DATE'], '%Y-%m-%d')
                end_date = datetime.strptime(CONFIG['CUSTOM_END_DATE'], '%Y-%m-%d')
                
                # 确保结束日期不晚于今天
                if end_date > now:
                    end_date = now
                
                # 确保开始日期不晚于结束日期
                if start_date > end_date:
                    start_date = end_date - timedelta(days=1)
                
                return {
                    'start_date': start_date,
                    'end_date': end_date,
                    'description': f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}",
                    'mode': 'custom_range'
                }
            except ValueError as e:
                print(f"⚠️ 自定义日期格式错误: {e}，使用默认设置")
        
        # 如果只设置了开始日期
        elif CONFIG['CUSTOM_START_DATE']:
            try:
                start_date = datetime.strptime(CONFIG['CUSTOM_START_DATE'], '%Y-%m-%d')
                if start_date > now:
                    start_date = now - timedelta(days=1)
                
                return {
                    'start_date': start_date,
                    'end_date': now,
                    'description': f"{start_date.strftime('%Y-%m-%d')} 至今",
                    'mode': 'from_date'
                }
            except ValueError as e:
                print(f"⚠️ 开始日期格式错误: {e}，使用默认设置")
        
        # 使用天数+小时数设置
        total_hours = CONFIG['HISTORY_DAYS'] * 24 + CONFIG['HISTORY_HOURS']
        if total_hours <= 0:
            total_hours = 24  # 默认24小时
        
        start_time = now - timedelta(hours=total_hours)
        
        return {
            'start_date': start_time,
            'end_date': now,
            'description': f"过去 {CONFIG['HISTORY_DAYS']} 天 {CONFIG['HISTORY_HOURS']} 小时",
            'mode': 'duration'
        }
        
    def load_frequency_words(self) -> List[str]:
        """加载频率词"""
        try:
            with open('frequency_words.txt', 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return []
                
                words = []
                for line in content.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#') and not line.startswith('!') and not line.startswith('+'):
                        words.append(line)
                return words
        except FileNotFoundError:
            print("⚠️ frequency_words.txt 文件不存在，将使用默认关键词")
            return ["AI", "人工智能", "股市", "房价", "新能源", "教育", "就业"]
        except Exception as e:
            print(f"⚠️ 读取frequency_words.txt失败: {e}")
            return []
    
    def load_filter_words(self) -> List[str]:
        """加载过滤词（以!开头）"""
        try:
            with open('frequency_words.txt', 'r', encoding='utf-8') as f:
                content = f.read().strip()
                words = []
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('!'):
                        words.append(line[1:])  # 去掉!号
                return words
        except:
            return []
    
    def load_must_words(self) -> List[str]:
        """加载必须词（以+开头）"""
        try:
            with open('frequency_words.txt', 'r', encoding='utf-8') as f:
                content = f.read().strip()
                words = []
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('+'):
                        words.append(line[1:])  # 去掉+号
                return words
        except:
            return []

    def fetch_platform_data(self, platform_id: str) -> List[Dict]:
        """获取指定平台的数据"""
        try:
            url = f"{CONFIG['API_BASE_URL']}/{platform_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': 'https://newsnow.cc/'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            # 根据不同平台的数据结构进行解析
            if isinstance(data, dict):
                news_list = data.get('data', data.get('list', []))
            elif isinstance(data, list):
                news_list = data
            else:
                return []
            
            results = []
            for i, item in enumerate(news_list[:CONFIG['MAX_RESULTS_PER_PLATFORM']], 1):
                processed_item = {
                    'title': self.clean_text(str(item.get('title', item.get('name', ''))).strip()),
                    'url': item.get('url', item.get('link', '')),
                    'rank': i,
                    'platform_id': platform_id,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'raw_data': item
                }
                
                if processed_item['title']:
                    results.append(processed_item)
            
            return results
            
        except requests.exceptions.Timeout:
            print(f"  ⏰ {platform_id} 请求超时")
            return []
        except requests.exceptions.RequestException as e:
            print(f"  ❌ {platform_id} 网络请求失败: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"  ❌ {platform_id} 数据解析失败: {e}")
            return []
        except Exception as e:
            print(f"  ❌ {platform_id} 未知错误: {e}")
            return []

    def clean_text(self, text: str) -> str:
        """清理文本"""
        if not text:
            return ""
        
        # HTML解码
        text = html.unescape(text)
        
        # 移除多余空白字符
        text = re.sub(r'\s+', ' ', text.strip())
        
        # 移除特殊字符但保留中文、英文、数字
        text = re.sub(r'[^\u4e00-\u9fff\w\s\-\.\!\?\,\:\;\(\)\[\]\"\'\/]', '', text)
        
        return text

    def collect_all_data(self) -> List[Dict]:
        """收集所有平台数据"""
        print(f"📊 开始收集 {len(PLATFORMS)} 个平台的数据...")
        
        all_data = []
        success_count = 0
        
        for platform_id, platform_name in PLATFORMS:
            try:
                print(f"  正在获取 {platform_name} 数据...")
                data = self.fetch_platform_data(platform_id)
                
                if data:
                    # 为每条数据添加平台信息
                    for item in data:
                        item['platform_name'] = platform_name
                    all_data.extend(data)
                    success_count += 1
                    print(f"    ✅ 获取到 {len(data)} 条数据")
                else:
                    print(f"    ⚠️ 未获取到数据")
                
                # 请求间隔
                time.sleep(CONFIG['REQUEST_DELAY'])
                
            except Exception as e:
                print(f"    ❌ {platform_name} 数据获取失败: {e}")
        
        print(f"📈 数据收集完成：{success_count}/{len(PLATFORMS)} 个平台成功，共 {len(all_data)} 条数据")
        return all_data

    def match_keywords(self, title: str) -> Tuple[List[str], bool]:
        """匹配关键词并检查过滤条件"""
        if not title:
            return [], False
        
        title_lower = title.lower()
        
        # 检查过滤词
        for filter_word in self.filter_words:
            if filter_word.lower() in title_lower:
                return [], True  # 被过滤
        
        # 检查必须词（所有必须词都必须包含）
        if self.must_words:
            must_match_count = 0
            for must_word in self.must_words:
                if must_word.lower() in title_lower:
                    must_match_count += 1
            
            if must_match_count < len(self.must_words):
                return [], False  # 必须词不完整
        
        # 检查频率词
        matched_words = []
        for word in self.frequency_words:
            if word.lower() in title_lower:
                matched_words.append(word)
        
        return matched_words, False

    def analyze_data(self) -> Dict[str, Any]:
        """分析数据"""
        print("🔍 开始数据分析...")
        
        # 基础统计
        total_items = len(self.all_data)
        platform_stats = Counter(item['platform_name'] for item in self.all_data)
        
        # 关键词匹配统计
        keyword_matches = defaultdict(list)
        filtered_count = 0
        matched_count = 0
        
        for item in self.all_data:
            title = item.get('title', '')
            matched_keywords, is_filtered = self.match_keywords(title)
            
            if is_filtered:
                filtered_count += 1
                continue
            
            if matched_keywords:
                matched_count += 1
                # 使用第一个匹配的关键词作为主要分类
                primary_keyword = matched_keywords[0]
                keyword_matches[primary_keyword].append({
                    'title': title,
                    'platform': item['platform_name'],
                    'rank': item.get('rank', 999),
                    'url': item.get('url', ''),
                    'timestamp': item.get('timestamp', ''),
                    'all_matched_keywords': matched_keywords
                })
        
        # 关键词热度排序
        keyword_popularity = {
            keyword: len(items) 
            for keyword, items in keyword_matches.items()
        }
        
        sorted_keywords = sorted(
            keyword_popularity.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        # 热门新闻排序（按排名）
        for keyword in keyword_matches:
            keyword_matches[keyword].sort(key=lambda x: x['rank'])
        
        analysis_result = {
            'total_items': total_items,
            'matched_count': matched_count,
            'filtered_count': filtered_count,
            'platform_stats': dict(platform_stats),
            'keyword_matches': dict(keyword_matches),
            'keyword_popularity': keyword_popularity,
            'sorted_keywords': sorted_keywords,
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'config_summary': {
                'frequency_words_count': len(self.frequency_words),
                'filter_words_count': len(self.filter_words),
                'must_words_count': len(self.must_words),
                'platforms_count': len(PLATFORMS)
            }
        }
        
        print(f"✅ 分析完成：总计 {total_items} 条数据，匹配 {matched_count} 条，过滤 {filtered_count} 条")
        return analysis_result

    def generate_feishu_report(self) -> Dict[str, Any]:
        """生成飞书推送报告"""
        result = self.analysis_result
        time_desc = self.time_range['description']
        
        if not result['keyword_matches']:
            return {
                'total_titles': f"0 {result['analysis_time']} 历史汇总",
                'timestamp': f"📊 分析时间：{result['analysis_time']}",
                'report_type': f"📅 时间范围：{time_desc}",
                'text': f"📭 暂无匹配的热点词汇\n\n{self.generate_no_match_suggestion()}"
            }
        
        # 生成主要内容
        text_parts = []
        total_matched = result['matched_count']
        
        # 概览信息
        text_parts.append(f"📊 热点数据概览")
        text_parts.append(f"📅 分析周期：{time_desc}")
        text_parts.append(f"• 总数据量：{result['total_items']} 条")
        text_parts.append(f"• 匹配热点：{result['matched_count']} 条")
        text_parts.append(f"• 关键词命中：{len(result['keyword_matches'])} 个")
        text_parts.append("")
        
        # 时间跨度信息
        if CONFIG['ENABLE_TREND_ANALYSIS'] and result.get('time_distribution'):
            text_parts.append("⏰ 时间分布：")
            for time_period, count in list(result['time_distribution'].items())[:5]:
                text_parts.append(f"• {time_period}：{count} 条")
            text_parts.append("")
        
        # 平台分布
        text_parts.append("📱 平台分布：")
        sorted_platforms = sorted(result['platform_stats'].items(), key=lambda x: x[1], reverse=True)
        for platform, count in sorted_platforms[:8]:  # 显示前8个平台
            text_parts.append(f"• {platform}：{count} 条")
        text_parts.append("")
        
        # 热门关键词
        text_parts.append("🔥 热门关键词排行：")
        for i, (keyword, count) in enumerate(result['sorted_keywords'][:CONFIG['TOP_KEYWORDS_LIMIT']], 1):
            # 计算关键词的趋势（如果启用了趋势分析）
            trend_indicator = ""
            if CONFIG['ENABLE_TREND_ANALYSIS'] and result.get('keyword_trends', {}).get(keyword):
                trend_data = result['keyword_trends'][keyword]
                if trend_data.get('is_rising'):
                    trend_indicator = " 📈"
                elif trend_data.get('is_declining'):
                    trend_indicator = " 📉"
                elif trend_data.get('is_stable'):
                    trend_indicator = " ➡️"
            
            text_parts.append(f"{i}. **{keyword}** - {count} 条{trend_indicator}")
        text_parts.append("")
        
        # 详细热点内容
        text_parts.append("📰 热点详情：")
        for keyword, count in result['sorted_keywords'][:5]:  # 详细显示前5个关键词
            text_parts.append(f"\n🔍 **{keyword}** ({count} 条)：")
            
            items = result['keyword_matches'][keyword][:CONFIG['TOP_NEWS_PER_KEYWORD']]
            for j, item in enumerate(items, 1):
                rank_indicator = f"[{item['rank']}]" if item['rank'] <= 5 else f"[{item['rank']}]"
                title_preview = item['title'][:60] + "..." if len(item['title']) > 60 else item['title']
                
                # 添加时间信息
                time_info = ""
                if item.get('item_time'):
                    time_str = item['item_time'].strftime('%m-%d %H:%M')
                    time_info = f" - {time_str}"
                
                text_parts.append(f"  {j}. [{item['platform']}] {title_preview} {rank_indicator}{time_info}")
        
        # 构建返回结果
        return {
            'total_titles': f"{total_matched} {result['analysis_time']} 历史汇总",
            'timestamp': f"⏰ 分析时间：{result['analysis_time']}",
            'report_type': f"📅 {time_desc} - {len(result['keyword_matches'])} 个关键词命中",
            'text': '\n'.join(text_parts)
        }

    def generate_no_match_suggestion(self) -> str:
        """生成无匹配时的建议"""
        suggestions = [
            "💡 优化建议：",
            "",
            "1. **扩大关键词范围**",
            "   • 添加更通用的词汇（如：科技、教育、健康）",
            "   • 减少过于具体的专业术语",
            "",
            "2. **检查过滤词设置**",
            f"   • 当前有 {len(self.filter_words)} 个过滤词",
            "   • 确认是否过度过滤",
            "",
            "3. **调整必须词逻辑**",
            f"   • 当前有 {len(self.must_words)} 个必须词",
            "   • 必须词要求同时包含，可能过于严格",
            "",
            "4. **当前配置状态**",
            f"   • 监控关键词：{len(self.frequency_words)} 个",
            f"   • 数据平台：{len(PLATFORMS)} 个",
            f"   • 总数据量：{self.analysis_result.get('total_items', 0)} 条",
            "",
            "建议先尝试添加一些通用热门关键词！"
        ]
        return '\n'.join(suggestions)

    def send_feishu_message(self, message_data: Dict[str, Any]) -> bool:
        """发送飞书消息"""
        if not CONFIG['FEISHU_WEBHOOK_URL']:
            print("⚠️ 未配置飞书Webhook URL，跳过推送")
            return False
        
        try:
            payload = {
                "msg_type": "text",
                "content": {
                    "text": f"{message_data['total_titles']}\n\n{message_data['timestamp']}\n{message_data['report_type']}\n\n{message_data['text']}"
                }
            }
            
            response = requests.post(
                CONFIG['FEISHU_WEBHOOK_URL'],
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                print("✅ 飞书消息发送成功")
                return True
            else:
                print(f"❌ 飞书消息发送失败，状态码：{response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 飞书消息发送异常：{e}")
            return False

    def save_html_report(self) -> None:
        """保存HTML报告"""
        try:
            # 确保输出目录存在
            today = datetime.now().strftime('%Y年%m月%d日')
            output_dir = f"output/{today}/html"
            os.makedirs(output_dir, exist_ok=True)
            
            html_content = self.generate_html_report()
            
            # 保存当日报告
            daily_file = f"{output_dir}/当日统计.html"
            with open(daily_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # 保存根目录index.html
            with open('index.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print(f"📄 HTML报告已保存：{daily_file}")
            
        except Exception as e:
            print(f"❌ HTML报告保存失败：{e}")

    def generate_html_report(self) -> str:
        """生成HTML报告"""
        result = self.analysis_result
        
        html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TrendRadar - 热点分析报告</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background: #f5f7fa; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 2.5em; font-weight: 700; }}
        .header p {{ margin: 10px 0 0; opacity: 0.9; font-size: 1.1em; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; padding: 30px; background: #f8f9ff; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
        .stat-number {{ font-size: 2.5em; font-weight: bold; color: #667eea; margin-bottom: 5px; }}
        .stat-label {{ color: #666; font-size: 0.9em; }}
        .content {{ padding: 30px; }}
        .section {{ margin-bottom: 40px; }}
        .section h2 {{ color: #333; border-bottom: 3px solid #667eea; padding-bottom: 10px; margin-bottom: 20px; }}
        .keyword-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }}
        .keyword-card {{ border: 1px solid #e1e5e9; border-radius: 8px; padding: 20px; background: #fff; }}
        .keyword-title {{ font-size: 1.3em; font-weight: bold; color: #667eea; margin-bottom: 15px; }}
        .news-item {{ margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 5px; border-left: 4px solid #667eea; }}
        .news-item a {{ text-decoration: none; color: #333; }}
        .news-item a:hover {{ color: #667eea; }}
        .platform-tag {{ display: inline-block; background: #e3f2fd; color: #1976d2; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 5px; }}
        .rank-high {{ background: #ffebee; color: #c62828; }}
        .rank-normal {{ background: #f3e5f5; color: #7b1fa2; }}
        .footer {{ text-align: center; padding: 20px; background: #f5f7fa; color: #666; }}
        .no-data {{ text-align: center; padding: 60px 20px; color: #666; }}
        .no-data h3 {{ color: #ff6b6b; margin-bottom: 20px; }}
        .suggestion {{ background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .suggestion h4 {{ color: #d68910; margin-top: 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 TrendRadar</h1>
            <p>多平台热点资讯监控分析系统 - 历史数据汇总</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{result.get('total_items', 0)}</div>
                <div class="stat-label">总数据量</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{result.get('matched_count', 0)}</div>
                <div class="stat-label">匹配热点</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(result.get('keyword_matches', {}))}</div>
                <div class="stat-label">关键词命中</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(PLATFORMS)}</div>
                <div class="stat-label">监控平台</div>
            </div>
        </div>
        
        <div class="content">
        """
        
        if result.get('keyword_matches'):
            html_template += f"""
            <div class="section">
                <h2>🔥 热门关键词排行</h2>
                <div class="keyword-grid">
            """
            
            for keyword, count in result['sorted_keywords'][:12]:  # 显示前12个
                items = result['keyword_matches'][keyword][:5]  # 每个关键词显示前5条
                
                html_template += f"""
                <div class="keyword-card">
                    <div class="keyword-title">{keyword} ({count} 条)</div>
                """
                
                for item in items:
                    rank_class = "rank-high" if item['rank'] <= 5 else "rank-normal"
                    url = item.get('url', '#')
                    
                    html_template += f"""
                    <div class="news-item">
                        <span class="platform-tag {rank_class}">{item['platform']} #{item['rank']}</span>
                        <br>
                        <a href="{url}" target="_blank" rel="noopener">{item['title']}</a>
                    </div>
                    """
                
                html_template += "</div>"
            
            html_template += "</div></div>"
            
        else:
            # 无数据时的显示
            suggestions = self.generate_no_match_suggestion()
            html_template += f"""
            <div class="no-data">
                <h3>📭 暂无匹配的热点数据</h3>
                <div class="suggestion">
                    <h4>💡 优化建议</h4>
                    <pre style="white-space: pre-line; text-align: left;">{suggestions}</pre>
                </div>
            </div>
            """
        
        html_template += f"""
        </div>
        
        <div class="footer">
            <p>📊 分析时间：{result.get('analysis_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))} | 
            💾 配置：{result.get('config_summary', {}).get('frequency_words_count', 0)} 个关键词，
            {result.get('config_summary', {}).get('platforms_count', 0)} 个平台</p>
            <p>⚡ Powered by TrendRadar - 让热点触手可及</p>
        </div>
    </div>
</body>
</html>
        """
        
        return html_template

    def run(self) -> None:
        """主运行函数"""
        print("🚀 TrendRadar 历史分析版启动...")
        print(f"📋 配置概览：{len(self.frequency_words)} 个关键词，{len(PLATFORMS)} 个平台")
        print(f"⏰ 分析时间范围：{self.time_range['description']}")
        
        # 显示时间设置帮助信息
        self.print_time_config_help()
        
        try:
            # 1. 收集数据
            self.all_data = self.collect_all_data()
            
            if not self.all_data:
                print("❌ 未获取到任何数据，程序终止")
                return
            
            # 2. 分析数据
            self.analysis_result = self.analyze_data()
            
            # 3. 生成并发送飞书报告
            if CONFIG['FEISHU_WEBHOOK_URL']:
                feishu_report = self.generate_feishu_report()
                self.send_feishu_message(feishu_report)
            elif not CONFIG['CONTINUE_WITHOUT_FEISHU']:
                print("⚠️ 未配置飞书推送且设置为不继续运行")
                return
            
            # 4. 保存HTML报告
            self.save_html_report()
            
            # 5. 输出统计信息
            self.print_summary()
            
            print("✅ TrendRadar 运行完成！")
            
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断程序")
        except Exception as e:
            print(f"❌ 程序运行失败：{e}")
            import traceback
            traceback.print_exc()

    def print_time_config_help(self) -> None:
        """打印时间配置帮助信息"""
        print("\n" + "="*60)
        print("⏰ 时间范围配置说明")
        print("="*60)
        print("当前使用模式：", self.time_range['mode'])
        print("当前时间范围：", self.time_range['description'])
        print()
        print("💡 如需修改时间设置，可在GitHub Secrets中添加：")
        print("   • HISTORY_DAYS=7        # 分析过去7天")
        print("   • HISTORY_HOURS=12      # 额外增加12小时")
        print("   • CUSTOM_START_DATE=2024-01-01  # 自定义开始日期")
        print("   • CUSTOM_END_DATE=2024-01-31    # 自定义结束日期")
        print()
        print("📝 示例配置：")
        print("   1. 分析过去3天：HISTORY_DAYS=3")
        print("   2. 分析过去1周：HISTORY_DAYS=7")
        print("   3. 分析特定月份：CUSTOM_START_DATE=2024-01-01, CUSTOM_END_DATE=2024-01-31")
        print("   4. 分析最近36小时：HISTORY_DAYS=1, HISTORY_HOURS=12")
        print("="*60)
        
        try:
            # 1. 收集数据
            self.all_data = self.collect_all_data()
            
            if not self.all_data:
                print("❌ 未获取到任何数据，程序终止")
                return
            
            # 2. 分析数据
            self.analysis_result = self.analyze_data()
            
            # 3. 生成并发送飞书报告
            if CONFIG['FEISHU_WEBHOOK_URL']:
                feishu_report = self.generate_feishu_report()
                self.send_feishu_message(feishu_report)
            elif not CONFIG['CONTINUE_WITHOUT_FEISHU']:
                print("⚠️ 未配置飞书推送且设置为不继续运行")
                return
            
            # 4. 保存HTML报告
            self.save_html_report()
            
            # 5. 输出统计信息
            self.print_summary()
            
            print("✅ TrendRadar 运行完成！")
            
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断程序")
        except Exception as e:
            print(f"❌ 程序运行失败：{e}")
            import traceback
            traceback.print_exc()

    def print_summary(self) -> None:
        """打印运行总结"""
        result = self.analysis_result
        print("\n" + "="*50)
        print("📊 运行总结")
        print("="*50)
        print(f"📈 数据收集：{result['total_items']} 条")
        print(f"🎯 关键词匹配：{result['matched_count']} 条")
        print(f"🚫 过滤数据：{result['filtered_count']} 条")
        print(f"🔥 热门关键词：{len(result['keyword_matches'])} 个")
        
        if result['sorted_keywords']:
            print(f"🏆 最热关键词：{result['sorted_keywords'][0][0]} ({result['sorted_keywords'][0][1]} 条)")
        
        print(f"⏰ 分析时间：{result['analysis_time']}")
        print("="*50)


def main():
    """主函数"""
    analyzer = TrendAnalyzer()
    analyzer.run()


if __name__ == "__main__":
    main()
