# -*- coding:utf-8 -*-
"""
美团红包定时任务脚本
从数据库读取所有启用的账号并执行领取

cron: 0 8,14 * * *
"""
import os
import sys
import json
from datetime import datetime

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meituan import grab_waimai_coupons, grab_tuangou_coupons


def get_db_path():
    """获取数据库路径"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_data_dir = '/app/data' if os.path.exists('/app') else os.path.join(script_dir, 'data')
    data_dir = os.environ.get('DATA_DIR', default_data_dir)
    return os.environ.get('DB_PATH', f'{data_dir}/meituan.db')


def get_active_accounts():
    """从数据库获取所有启用的账号"""
    import sqlite3
    
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        print(f"[错误] 数据库文件不存在: {db_path}")
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查询所有启用的账号
        cursor.execute("""
            SELECT id, name, token 
            FROM meituan_accounts 
            WHERE is_active = 1
        """)
        
        accounts = []
        for row in cursor.fetchall():
            accounts.append({
                'id': row[0],
                'name': row[1],
                'token': row[2]
            })
        
        conn.close()
        return accounts
        
    except Exception as e:
        print(f"[错误] 读取数据库失败: {e}")
        return []


def save_grab_history(account_id, status, success_count, failed_count, details, raw_output):
    """保存领取历史到数据库"""
    import sqlite3
    
    db_path = get_db_path()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 插入领取历史
        cursor.execute("""
            INSERT INTO grab_histories 
            (account_id, grab_time, status, total_coupons, success_count, failed_count, details, raw_output)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            account_id,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            status,
            success_count + failed_count,
            success_count,
            failed_count,
            json.dumps(details, ensure_ascii=False),
            raw_output
        ))
        
        # 更新账号最后执行时间和状态
        cursor.execute("""
            UPDATE meituan_accounts 
            SET last_run_at = ?, last_run_status = ?
            WHERE id = ?
        """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), status, account_id))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"[错误] 保存历史记录失败: {e}")


def parse_output(output):
    """解析领取输出"""
    result = {'success': 0, 'failed': 0, 'coupons': []}
    
    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue
        if '成功领取' in line:
            result['success'] += 1
            result['coupons'].append({'name': line, 'status': 'success'})
        elif '领取失败' in line or '请求异常' in line:
            result['failed'] += 1
            result['coupons'].append({'name': line, 'status': 'failed'})
    
    return result


def run_grab_for_account(account):
    """为单个账号执行领取"""
    import io
    import contextlib
    
    account_id = account['id']
    name = account['name']
    token = account['token']
    
    print(f"\n账号: {name}")
    print("-" * 50)
    
    # 捕获输出
    output_buffer = io.StringIO()
    
    waimai_success = False
    tuangou_success = False
    
    # 领取外卖红包
    with contextlib.redirect_stdout(output_buffer):
        try:
            waimai_success = grab_waimai_coupons(token)
        except Exception as e:
            print(f"[外卖] 执行异常: {e}")
    
    # 领取团购红包
    with contextlib.redirect_stdout(output_buffer):
        try:
            tuangou_success = grab_tuangou_coupons(token)
        except Exception as e:
            print(f"[团购] 执行异常: {e}")
    
    raw_output = output_buffer.getvalue()
    
    # 同时打印到控制台
    print(raw_output)
    
    # 解析结果
    parsed = parse_output(raw_output)
    
    # 判断状态
    status = 'success' if (waimai_success or tuangou_success) else 'failed'
    
    # 保存历史记录
    save_grab_history(
        account_id=account_id,
        status=status,
        success_count=parsed['success'],
        failed_count=parsed['failed'],
        details=parsed['coupons'],
        raw_output=raw_output
    )
    
    return status == 'success'


def main():
    """主函数：从数据库读取账号并执行领取"""
    print("=" * 50)
    print("美团红包定时任务 - 开始执行")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 获取所有启用的账号
    accounts = get_active_accounts()
    
    if not accounts:
        # 如果数据库中没有账号，尝试从环境变量获取
        token = os.environ.get('MEITUAN_TOKEN', '').strip()
        if token:
            print("\n使用环境变量 MEITUAN_TOKEN")
            tokens = [t.strip() for t in token.replace('\n', '&').split('&') if t.strip()]
            for i, tk in enumerate(tokens, 1):
                print(f"\n环境变量账号 {i}/{len(tokens)}")
                print("-" * 50)
                grab_waimai_coupons(tk)
                grab_tuangou_coupons(tk)
        else:
            print("\n[警告] 没有可执行的账号")
            print("请通过 Web 控制台添加账号，或设置 MEITUAN_TOKEN 环境变量")
        return
    
    print(f"\n找到 {len(accounts)} 个启用的账号")
    
    # 执行领取
    success_count = 0
    for i, account in enumerate(accounts, 1):
        print(f"\n[{i}/{len(accounts)}] 处理账号: {account['name']}")
        
        if run_grab_for_account(account):
            success_count += 1
    
    print("\n" + "=" * 50)
    print(f"执行完成: {success_count}/{len(accounts)} 个账号成功")
    print("=" * 50)


if __name__ == '__main__':
    main()
