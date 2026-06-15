"""
校园二手交易平台 - Streamlit 单文件应用
功能：发布闲置、浏览/搜索商品、收藏管理、JSON 持久化
"""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st

# 缓存数据，避免频繁读写文件
_data_cache = None
_cache_time = 0


def get_cached_data() -> dict:
    global _data_cache, _cache_time
    current_time = datetime.now().timestamp()
    # 5秒内使用缓存
    if _data_cache is not None and current_time - _cache_time < 5:
        return _data_cache
    _data_cache = load_data()
    _cache_time = current_time
    return _data_cache


def invalidate_cache() -> None:
    global _data_cache
    _data_cache = None


def hash_password(password: str) -> str:
    if not password:
        return ""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(stored_hash: str, password: str) -> bool:
    if not stored_hash or not password:
        return False
    return stored_hash == hashlib.sha256(password.encode()).hexdigest()

# ─── 数据层 ─────────────────────────────────────────────
DATA_FILE = Path("data.json")

DEFAULT_DATA = {"items": [], "next_id": 1, "users": [], "next_user_id": 1}


def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            # 兼容旧数据，确保所有字段都存在
            if "users" not in data:
                data["users"] = []
            if "next_user_id" not in data:
                data["next_user_id"] = 1
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_DATA.copy()


def save_data(data: dict) -> None:
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_all_items() -> list:
    return get_cached_data().get("items", [])


def add_item(title: str, desc: str, price: float, category: str,
             contact: str, admin_password: str = "", user_id: Optional[int] = None) -> None:
    data = get_cached_data()
    item = {
        "id": data["next_id"],
        "title": title,
        "description": desc,
        "price": price,
        "category": category,
        "contact": contact,
        "admin_password": hash_password(admin_password),
        "user_id": user_id,  # 发帖者用户ID，None表示未登录发布
        "messages": [],  # 每条消息: {name, contact, content, time}
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data["items"].insert(0, item)
    data["next_id"] += 1
    save_data(data)
    invalidate_cache()


def add_message(item_id: int, name: str, contact: str, content: str) -> None:
    data = get_cached_data()
    for item in data["items"]:
        if item["id"] == item_id:
            item.setdefault("messages", []).append({
                "name": name.strip() or "匿名买家",
                "contact": contact.strip(),
                "content": content.strip(),
                "time": datetime.now().strftime("%m-%d %H:%M"),
            })
            break
    save_data(data)
    invalidate_cache()


def toggle_favorite(item_id: int) -> None:
    fav = st.session_state.favorites
    if item_id in fav:
        fav.remove(item_id)
    else:
        fav.add(item_id)


def delete_item(item_id: int) -> bool:
    data = get_cached_data()
    original_count = len(data["items"])
    data["items"] = [item for item in data["items"] if item["id"] != item_id]
    if len(data["items"]) < original_count:
        save_data(data)
        invalidate_cache()
        # 同时从收藏中移除
        if item_id in st.session_state.favorites:
            st.session_state.favorites.remove(item_id)
        return True
    return False


def get_item_by_id(item_id: int) -> Optional[dict]:
    items = get_all_items()
    for item in items:
        if item["id"] == item_id:
            return item
    return None


# ─── 用户相关函数 ───────────────────────────────────────
def get_users() -> list:
    return get_cached_data().get("users", [])


def get_user_by_username(username: str) -> Optional[dict]:
    users = get_users()
    for user in users:
        if user["username"] == username:
            return user
    return None


def get_user_by_id(user_id: int) -> Optional[dict]:
    users = get_users()
    for user in users:
        if user["id"] == user_id:
            return user
    return None


def register_user(username: str, password: str, contact: str) -> dict:
    """注册新用户，返回 {"success": bool, "message": str}"""
    if not username.strip():
        return {"success": False, "message": "用户名不能为空"}
    if not password:
        return {"success": False, "message": "密码不能为空"}
    
    if get_user_by_username(username.strip()):
        return {"success": False, "message": "用户名已存在"}
    
    data = get_cached_data()
    user = {
        "id": data["next_user_id"],
        "username": username.strip(),
        "password_hash": hash_password(password),
        "contact": contact.strip(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data["users"].append(user)
    data["next_user_id"] += 1
    save_data(data)
    invalidate_cache()
    return {"success": True, "message": "注册成功", "user": user}


def login_user(username: str, password: str) -> dict:
    """用户登录，返回 {"success": bool, "message": str, "user": dict}"""
    user = get_user_by_username(username.strip())
    if not user:
        return {"success": False, "message": "用户名不存在"}
    
    # 兼容旧数据（未哈希的密码）
    pw_hash = user["password_hash"]
    if len(pw_hash) == 64:
        # 已哈希密码
        if not verify_password(pw_hash, password):
            return {"success": False, "message": "密码错误"}
    else:
        # 旧数据明文密码
        if pw_hash != password:
            return {"success": False, "message": "密码错误"}
    
    return {"success": True, "message": "登录成功", "user": user}


def logout_user() -> None:
    """退出登录"""
    if "current_user" in st.session_state:
        del st.session_state["current_user"]


# ─── 公共组件 ───────────────────────────────────────────
def render_login_register_panel() -> None:
    """渲染登录/注册面板"""
    st.header("👤 用户登录")
    
    # 切换登录/注册模式
    login_tab, register_tab = st.tabs(["登录", "注册"])
    
    with login_tab:
        with st.form("login_form", clear_on_submit=True):
            username = st.text_input("用户名", placeholder="请输入用户名")
            password = st.text_input("密码", type="password", placeholder="请输入密码")
            if st.form_submit_button("登录", type="primary", use_container_width=True):
                result = login_user(username, password)
                if result["success"]:
                    st.session_state["current_user"] = result["user"]
                    st.success("✅ 登录成功！")
                    st.rerun()
                else:
                    st.error(result["message"])
    
    with register_tab:
        with st.form("register_form", clear_on_submit=True):
            username = st.text_input("用户名", placeholder="请输入用户名（支持中文）")
            password = st.text_input("密码", type="password", placeholder="请输入密码")
            contact = st.text_input("联系方式", placeholder="微信 / QQ / 手机号")
            if st.form_submit_button("注册", type="primary", use_container_width=True):
                result = register_user(username, password, contact)
                if result["success"]:
                    st.session_state["current_user"] = result["user"]
                    st.success("✅ 注册成功！")
                    st.rerun()
                else:
                    st.error(result["message"])


def render_user_info_panel() -> None:
    """渲染已登录用户信息面板"""
    user = st.session_state["current_user"]
    st.header("👤 个人中心")
    
    st.markdown(f"""
    <div style="background:#e8f5e9;border-radius:8px;padding:1rem;margin-bottom:1rem;border-left:3px solid #4caf50">
        <div><b>用户名</b>：{user['username']}</div>
        <div><b>联系方式</b>：{user.get('contact', '未设置')}</div>
        <div><b>注册时间</b>：{user['created_at']}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # 我的发布
    st.subheader("📦 我的发布")
    items = get_all_items()
    user_items = [item for item in items if item.get("user_id") == user["id"]]
    
    if not user_items:
        st.info("还没有发布任何商品")
    else:
        st.caption(f"共发布了 {len(user_items)} 件商品")
        for item in user_items:
            iid = item["id"]
            st.markdown(f"""<div class="card">
            <div style="display:flex;justify-content:space-between;align-items:start">
                <div>
                    <h4>{item['title']}</h4>
                    <span class="tag">{item['category']}</span>
                    <span class="meta"> {item['created_at']}</span>
                </div>
                <div class="price">¥{item['price']:.2f}</div>
            </div>
            <p style="margin:0.5rem 0">{item['description']}</p>
            </div>""", unsafe_allow_html=True)
            
            # 直接显示留言（无需密码验证）
            msgs = item.get("messages", [])
            if msgs:
                st.caption(f"📩 共 {len(msgs)} 条留言")
                for m in msgs:
                    st.markdown(f"""
                    <div style="background:#fff8e1;border-radius:8px;padding:0.6rem 1rem;margin-bottom:0.5rem;border-left:3px solid #ffa000;color:#333333">
                        <div><b>{m['name']}</b> <span class="meta">({m.get('contact','')})  · {m['time']}</span></div>
                        <div style="margin-top:0.3rem">{m['content']}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("暂无留言")
            
            # 删除帖子按钮
            if st.button(f"🗑️ 删除帖子 {item['title']}", key=f"user_del_{iid}", type="secondary"):
                st.session_state[f"confirm_del_{iid}"] = True
            
            # 删除确认对话框
            if st.session_state.get(f"confirm_del_{iid}", False):
                st.warning("⚠️ 确认要删除此帖子吗？此操作不可撤销！")
                del_cols = st.columns(2)
                with del_cols[0]:
                    if st.button(f"✅ 确认删除", key=f"user_confirm_{iid}"):
                        if delete_item(iid):
                            st.success("✅ 帖子已删除！")
                        else:
                            st.error("❌ 删除失败")
                        st.session_state[f"confirm_del_{iid}"] = False
                        st.rerun()
                with del_cols[1]:
                    if st.button(f"❌ 取消", key=f"user_cancel_del_{iid}"):
                        st.session_state[f"confirm_del_{iid}"] = False
                        st.rerun()
            
            st.divider()
    
    if st.button("🚪 退出登录", type="secondary", use_container_width=True):
        logout_user()
        st.success("已退出登录")
        st.rerun()


def render_item_card(item: dict) -> None:
    """渲染商品卡片"""
    # 获取发布者用户名
    user_id = item.get("user_id")
    if user_id:
        user = get_user_by_id(user_id)
        username = user["username"] if user else "未知用户"
        user_display = f"<span class='tag' style='background:#e8f5e9;color:#4caf50'>👤 {username}</span>"
    else:
        user_display = "<span class='tag' style='background:#f5f5f5;color:#666'>👤 匿名发布</span>"
    
    st.markdown(f"""<div class="card">
    <div style="display:flex;justify-content:space-between;align-items:start">
        <div>
            <h4>{item['title']}</h4>
            {user_display}
            <span class="tag">{item['category']}</span>
            <span class="meta"> {item['created_at']}</span>
        </div>
        <div class="price">¥{item['price']:.2f}</div>
    </div>
    <p style="margin:0.5rem 0">{item['description']}</p>
    </div>""", unsafe_allow_html=True)


def render_message_form(item_id: int, key_prefix: str = "") -> None:
    """渲染留言表单"""
    show_key = f"show_msg_{item_id}"
    form_key = f"{key_prefix}msg_form_{item_id}"
    name_key = f"{key_prefix}fn_{item_id}" if key_prefix else None
    contact_key = f"{key_prefix}fc_{item_id}" if key_prefix else None
    content_key = f"{key_prefix}fm_{item_id}" if key_prefix else None
    
    # 获取当前登录用户信息
    current_user = st.session_state.get("current_user")
    default_name = current_user["username"] if current_user else ""
    default_contact = current_user.get("contact", "") if current_user else ""
    
    if st.session_state.get(show_key, False):
        with st.form(key=form_key, clear_on_submit=True):
            st.caption("💬 给卖家留言")
            mc1, mc2 = st.columns(2)
            with mc1:
                msg_name = st.text_input("你的昵称", value=default_name, placeholder="可选", key=name_key)
            with mc2:
                msg_contact = st.text_input("你的联系方式", value=default_contact, placeholder="微信 / QQ", key=contact_key)
            msg_content = st.text_area("留言内容", height=80, max_chars=300, key=content_key)
            if st.form_submit_button("发送留言", type="primary"):
                if not msg_content.strip():
                    st.error("请填写留言内容")
                else:
                    add_message(item_id, msg_name, msg_contact, msg_content)
                    st.success("✅ 留言已发送！卖家将尽快回复")
                    st.session_state[show_key] = False
                    st.rerun()


def render_admin_panel(item: dict, key_prefix: str = "") -> None:
    """渲染留言管理面板（含删除功能）"""
    iid = item["id"]
    show_key = f"show_admin_{iid}"
    pw_key = f"{key_prefix}pw_{iid}" if key_prefix else f"pw_{iid}"
    del_key = f"{key_prefix}del_{iid}" if key_prefix else f"del_{iid}"
    confirm_key = f"{key_prefix}confirm_{iid}" if key_prefix else f"confirm_{iid}"
    cancel_key = f"{key_prefix}cancel_del_{iid}" if key_prefix else f"cancel_del_{iid}"
    
    # 获取当前登录用户
    current_user = st.session_state.get("current_user")
    current_user_id = current_user["id"] if current_user else None
    
    # 判断是否为帖子所有者
    item_user_id = item.get("user_id")
    is_owner = current_user_id is not None and item_user_id == current_user_id
    
    if st.session_state.get(show_key, False):
        pw = item.get("admin_password", "")
        can_view = True
        
        # 如果是帖子所有者，直接可以查看和删除
        if is_owner:
            can_view = True
        elif pw and len(pw) != 64:  # 旧数据明文密码
            entered = st.text_input("输入管理密码查看留言", type="password", key=pw_key)
            can_view = (entered == pw)
            if entered and not can_view:
                st.error("密码错误")
        elif pw:
            entered = st.text_input("输入管理密码查看留言", type="password", key=pw_key)
            can_view = verify_password(pw, entered)
            if entered and not can_view:
                st.error("密码错误")
        
        if can_view:
            contact_info = item.get('contact', '未设置')
            st.markdown(f"""
            <div style="background:#e3f2fd;border-radius:8px;padding:0.5rem 1rem;margin-bottom:0.8rem;border-left:3px solid #1a73e8">
                <b>📞 你的联系方式</b>：{contact_info}
            </div>
            """, unsafe_allow_html=True)
            
            # 判断是否有权限删除
            can_delete = is_owner  # 已登录用户发布的帖子
            if not can_delete and item_user_id is None:
                # 未登录发布的帖子或历史帖子，使用管理密码验证删除
                can_delete = True  # 已经通过密码验证才能看到这里
            
            if can_delete:
                # 删除帖子按钮
                if st.button("🗑️ 删除帖子", key=del_key, type="secondary"):
                    st.session_state[f"confirm_del_{iid}"] = True
                
                # 删除确认对话框
                if st.session_state.get(f"confirm_del_{iid}", False):
                    st.warning("⚠️ 确认要删除此帖子吗？此操作不可撤销！")
                    del_cols = st.columns(2)
                    with del_cols[0]:
                        if st.button("✅ 确认删除", key=confirm_key):
                            if delete_item(iid):
                                st.success("✅ 帖子已删除！")
                            else:
                                st.error("❌ 删除失败")
                            st.session_state[show_key] = False
                            st.session_state[f"confirm_del_{iid}"] = False
                            st.rerun()
                    with del_cols[1]:
                        if st.button("❌ 取消", key=cancel_key):
                            st.session_state[f"confirm_del_{iid}"] = False
                            st.rerun()
            else:
                st.warning("⚠️ 你不是该帖子的发布者，无法删除")
            
            msgs = item.get("messages", [])
            if not msgs:
                st.info("暂无留言")
            else:
                st.caption(f"📩 共 {len(msgs)} 条留言（仅卖家可见）")
                for m in msgs:
                    st.markdown(f"""
                    <div style="background:#fff8e1;border-radius:8px;padding:0.6rem 1rem;margin-bottom:0.5rem;border-left:3px solid #ffa000;color:#333333">
                        <div><b>{m['name']}</b> <span class="meta">({m.get('contact','')})  · {m['time']}</span></div>
                        <div style="margin-top:0.3rem">{m['content']}</div>
                    </div>
                    """, unsafe_allow_html=True)


# ─── 页面配置 ───────────────────────────────────────────
st.set_page_config(page_title="校园二手集市", page_icon="📦", layout="centered")

# 初始化 session_state
if "favorites" not in st.session_state:
    st.session_state.favorites = set()
    # 从已加载的商品中恢复收藏状态（首次加载时）
    fav_ids = {i["id"] for i in get_all_items() if i.get("favorited")}
    st.session_state.favorites = fav_ids

# ─── 自定义样式 ─────────────────────────────────────────
st.markdown("""
<style>
    .card {
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 1.2rem 1rem;
        margin-bottom: 1rem;
        background: #fafafa;
    }
    .card h4 { margin: 0 0 0.3rem 0;color: #333333 }
    .price { color: #e74c3c; font-weight: bold; font-size: 1.2rem; }
    .tag {
        display: inline-block;
        background: #e8f0fe;
        color: #1a73e8;
        padding: 0.15rem 0.6rem;
        border-radius: 20px;
        font-size: 0.8rem;
    }
    .meta { color: #888; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

# ─── 侧边栏导航 ─────────────────────────────────────────
st.sidebar.title("📦 校园二手集市")

# 登录状态显示
current_user = st.session_state.get("current_user")
if current_user:
    st.sidebar.success(f"已登录：{current_user['username']}")
else:
    st.sidebar.info("请先登录")

# 导航菜单
nav_options = ["浏览商品", "发布闲置", "我的收藏", "用户中心"]
page = st.sidebar.radio("导航", nav_options)

# ─── 页面：发布闲置 ─────────────────────────────────────
if page == "发布闲置":
    st.header("📤 发布闲置")
    
    # 检查登录状态
    current_user = st.session_state.get("current_user")
    if not current_user:
        st.warning("⚠️ 请先登录后再发布闲置物品")
    else:
        # 获取当前用户信息
        default_contact = current_user.get("contact", "") if current_user else ""
        user_id = current_user["id"] if current_user else None
        
        with st.form("publish_form", clear_on_submit=True):
            title = st.text_input("商品名称 *", max_chars=50)
            desc = st.text_area("商品描述", max_chars=500, height=100)
            col1, col2 = st.columns(2)
            with col1:
                price = st.number_input("价格 (¥) *", min_value=0.0, step=1.0, format="%.2f")
            with col2:
                category = st.selectbox("分类 *", ["电子产品", "教材书籍", "生活用品", "服饰", "其他"])
            contact = st.text_input("联系方式", value=default_contact, 
                                   placeholder="微信 / QQ / 手机号")
            admin_password = st.text_input("管理密码（查看留言时用）", type="password",
                                           placeholder="留空则留言公开，若填写则只有物主可查看留言")
            submitted = st.form_submit_button("发布", type="primary", use_container_width=True)

            if submitted:
                if not title.strip():
                    st.error("请填写商品名称")
                elif price <= 0:
                    st.error("价格必须大于 0")
                else:
                    add_item(title.strip(), desc.strip(), price, category,
                             contact.strip(), admin_password.strip(), user_id)
                    st.success("✅ 发布成功！")
                    st.rerun()

# ─── 页面：浏览商品 ─────────────────────────────────────
elif page == "浏览商品":
    st.header("🔍 全部商品")
    items = get_all_items()

    # 初始化分类筛选状态
    if "cat_filter" not in st.session_state:
        st.session_state.cat_filter = "全部"

    # 搜索框
    keyword = st.text_input("搜索", placeholder="输入关键词…", label_visibility="collapsed")

    # 分类按钮组（点击即筛选）
    cats = ["全部", "电子产品", "教材书籍", "生活用品", "服饰", "其他"]
    cols = st.columns(len(cats))
    for i, cat in enumerate(cats):
        with cols[i]:
            active = st.session_state.cat_filter == cat
            btn_type = "primary" if active else "secondary"
            if st.button(cat, type=btn_type, use_container_width=True, key=f"cat_{cat}"):
                st.session_state.cat_filter = cat
                st.rerun()

    # 过滤
    filtered = items
    if st.session_state.cat_filter != "全部":
        filtered = [i for i in filtered if i["category"] == st.session_state.cat_filter]
    if keyword.strip():
        kw = keyword.lower()
        filtered = [i for i in filtered if kw in i["title"].lower() or kw in i["description"].lower()]

    if not filtered:
        st.info("暂无匹配商品")
    else:
        st.caption(f"共 {len(filtered)} 件商品")
        for item in filtered:
            is_fav = item["id"] in st.session_state.favorites
            fav_btn = "❤️" if is_fav else "🤍"
            with st.container():
                render_item_card(item)

            # 操作按钮行
            iid = item["id"]
            cols = st.columns(4)
            with cols[0]:
                if st.button(fav_btn, key=f"fav_{iid}"):
                    toggle_favorite(iid)
                    st.rerun()
            with cols[1]:
                if st.button("💬 留言", key=f"msg_btn_{iid}"):
                    st.session_state[f"show_msg_{iid}"] = not st.session_state.get(f"show_msg_{iid}", False)
                    st.rerun()
            with cols[2]:
                if st.button("📩 留言管理", key=f"admin_btn_{iid}"):
                    st.session_state[f"show_admin_{iid}"] = not st.session_state.get(f"show_admin_{iid}", False)
                    st.rerun()
            with cols[3]:
                st.empty()

            # 留言表单和管理面板
            render_message_form(iid)
            render_admin_panel(item)

# ─── 页面：我的收藏 ─────────────────────────────────────
elif page == "我的收藏":
    st.header("❤️ 我的收藏")
    items = get_all_items()
    fav_items = [i for i in items if i["id"] in st.session_state.favorites]

    if not fav_items:
        st.info("还没有收藏任何商品，去浏览页收藏吧！")
    else:
        st.caption(f"共 {len(fav_items)} 件收藏")
        for item in fav_items:
            iid = item["id"]
            with st.container():
                render_item_card(item)
            cols = st.columns(3)
            with cols[0]:
                if st.button("❤️ 取消收藏", key=f"unfav_{iid}"):
                    toggle_favorite(iid)
                    st.rerun()
            with cols[1]:
                if st.button("💬 留言", key=f"fav_msg_btn_{iid}"):
                    st.session_state[f"show_msg_{iid}"] = not st.session_state.get(f"show_msg_{iid}", False)
                    st.rerun()
            with cols[2]:
                if st.button("📩 留言管理", key=f"fav_admin_btn_{iid}"):
                    st.session_state[f"show_admin_{iid}"] = not st.session_state.get(f"show_admin_{iid}", False)
                    st.rerun()

            # 留言表单和管理面板（使用 fav_ 前缀区分）
            render_message_form(iid, "fav_")
            render_admin_panel(item, "fav_")

# ─── 页面：用户中心 ─────────────────────────────────────
elif page == "用户中心":
    current_user = st.session_state.get("current_user")
    if current_user:
        render_user_info_panel()
    else:
        render_login_register_panel()