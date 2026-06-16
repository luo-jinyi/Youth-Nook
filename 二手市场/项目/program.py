"""
校园二手交易平台 - Streamlit 单文件应用
功能：发布闲置、浏览/搜索商品、收藏管理、JSON 持久化、照片上传
"""
import base64
import hashlib
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st
from PIL import Image

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


def compress_image(image_bytes: bytes, max_size: int = 1024) -> bytes:
    """
    压缩图片到指定最大尺寸
    :param image_bytes: 原始图片字节
    :param max_size: 最大边长（像素）
    :return: 压缩后的图片字节
    """
    img = Image.open(io.BytesIO(image_bytes))
    
    # 获取原始尺寸
    width, height = img.size
    
    # 计算缩放比例
    scale = min(max_size / width, max_size / height)
    if scale < 1:
        new_width = int(width * scale)
        new_height = int(height * scale)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # 保存为JPEG格式
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def image_to_base64(image_bytes: bytes) -> str:
    """将图片字节转换为Base64编码字符串"""
    return base64.b64encode(image_bytes).decode("utf-8")


def upload_images(max_images: int = 5) -> list:
    """
    上传多张图片
    :param max_images: 最大上传数量
    :return: Base64编码的图片列表
    """
    uploaded_files = st.file_uploader(
        f"选择商品照片（最多{max_images}张，支持JPG/PNG/GIF）",
        type=["jpg", "jpeg", "png", "gif"],
        accept_multiple_files=True,
        key="image_uploader"
    )
    
    images_base64 = []
    if uploaded_files:
        for i, file in enumerate(uploaded_files):
            if i >= max_images:
                st.warning(f"最多只能上传{max_images}张图片")
                break
            
            # 读取文件内容
            file_bytes = file.read()
            
            # 检查大小（单张最大10MB）
            if len(file_bytes) > 10 * 1024 * 1024:
                st.warning(f"第{i+1}张图片超过10MB限制，已跳过")
                continue
            
            # 压缩图片
            compressed_bytes = compress_image(file_bytes)
            
            # 转换为Base64
            base64_str = image_to_base64(compressed_bytes)
            images_base64.append(base64_str)
            
            # 显示预览
            st.image(compressed_bytes, caption=f"图片 {i+1}", width=600)
    
    return images_base64

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
             contact: str, messages_visibility: str = "private", user_id: Optional[int] = None,
             images_base64: list = None) -> None:
    data = get_cached_data()
    item = {
        "id": data["next_id"],
        "title": title,
        "description": desc,
        "price": price,
        "category": category,
        "contact": contact,
        "messages_visibility": messages_visibility,  # "private" - 仅自己可见, "public" - 公开
        "user_id": user_id,  # 发帖者用户ID，None表示未登录发布
        "images": images_base64 or [],  # Base64编码的图片列表
        "messages": [],  # 每条消息: {name, contact, content, time}
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data["items"].insert(0, item)
    data["next_id"] += 1
    save_data(data)
    invalidate_cache()


def add_message(item_id: int, name: str, contact: str, content: str, user_id: Optional[int] = None) -> None:
    data = get_cached_data()
    for item in data["items"]:
        if item["id"] == item_id:
            item.setdefault("messages", []).append({
                "name": name.strip() or "匿名买家",
                "contact": contact.strip(),
                "content": content.strip(),
                "time": datetime.now().strftime("%m-%d %H:%M"),
                "user_id": user_id,  # 记录留言者用户ID
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


def delete_user(user_id: int) -> bool:
    """注销用户账号"""
    data = get_cached_data()
    
    # 获取要删除的用户信息（用于匹配旧数据中的用户名）
    user_to_delete = get_user_by_id(user_id)
    username_to_delete = user_to_delete["username"] if user_to_delete else ""
    
    # 先删除该用户在所有商品下的留言（包括自己发布的商品）
    for item in data["items"]:
        if "messages" in item:
            item["messages"] = [
                msg for msg in item["messages"] 
                if msg.get("user_id") != user_id and 
                   (msg.get("user_id") is not None or msg.get("name") != username_to_delete)
            ]
    
    # 再删除用户发布的所有商品
    data["items"] = [item for item in data["items"] if item.get("user_id") != user_id]
    
    # 删除用户账号
    original_user_count = len(data["users"])
    data["users"] = [user for user in data["users"] if user["id"] != user_id]
    
    if len(data["users"]) < original_user_count:
        save_data(data)
        invalidate_cache()
        return True
    return False


def check_username_duplicate(username: str) -> bool:
    """检查用户名是否重复"""
    if not username.strip():
        return False
    return get_user_by_username(username.strip()) is not None


def check_password_duplicate(password: str) -> bool:
    """检查密码是否与其他用户重复"""
    if not password:
        return False
    new_pw_hash = hash_password(password)
    users = get_users()
    for user in users:
        existing_pw_hash = user.get("password_hash", "")
        # 兼容新旧数据格式
        if existing_pw_hash == new_pw_hash or (len(existing_pw_hash) != 64 and existing_pw_hash == password):
            return True
    return False


def register_user(username: str, password: str, contact: str) -> dict:
    """注册新用户，返回 {"success": bool, "message": str}"""
    if not username.strip():
        return {"success": False, "message": "用户名不能为空"}
    if not password:
        return {"success": False, "message": "密码不能为空"}
    
    if check_username_duplicate(username):
        return {"success": False, "message": "用户名已存在"}
    
    if check_password_duplicate(password):
        return {"success": False, "message": "该密码已被其他用户使用，请选择其他密码"}
    
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
        # 用户名输入（实时验证）
        username = st.text_input("用户名", placeholder="请输入用户名（支持中文）", key="reg_username")
        if username.strip():
            if check_username_duplicate(username):
                st.markdown("<span style='color:red;font-size:0.8rem'>⚠️ 用户名已存在，请更换</span>", unsafe_allow_html=True)
            else:
                st.markdown("<span style='color:green;font-size:0.8rem'>✓ 用户名可用</span>", unsafe_allow_html=True)
        
        # 密码输入（实时验证）
        password = st.text_input("密码", type="password", placeholder="请输入密码", key="reg_password")
        if password:
            if check_password_duplicate(password):
                st.markdown("<span style='color:red;font-size:0.8rem'>⚠️ 该密码已被其他用户使用，请更换</span>", unsafe_allow_html=True)
            else:
                st.markdown("<span style='color:green;font-size:0.8rem'>✓ 密码可用</span>", unsafe_allow_html=True)
        
        # 联系方式输入
        contact = st.text_input("联系方式", placeholder="微信 / QQ / 手机号", key="reg_contact")
        
        # 注册按钮
        if st.button("注册", type="primary", use_container_width=True, key="reg_submit"):
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
            
            # 使用 Streamlit 原生组件构建卡片
            with st.container():
                # 标题和价格
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.subheader(item['title'])
                    st.markdown(f"{item['category']} · {item['created_at']}")
                with col2:
                    st.markdown(f"<h2 style='color:#e74c3c;text-align:right;margin:0'>¥{item['price']:.2f}</h2>", unsafe_allow_html=True)
                
                # 描述
                st.markdown(item['description'])
                
                # 图片
                images = item.get("images", [])
                if images:
                    display_images = images[:3]
                    for img_base64 in display_images:
                        st.image(f"data:image/jpeg;base64,{img_base64}", width=150)
                    if len(images) > 3:
                        st.caption(f"📷 共 {len(images)} 张图片")
            
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
    
    # 退出登录按钮（上面）
    if st.button("🚪 退出登录", type="secondary", use_container_width=True):
        logout_user()
        st.success("已退出登录")
        st.rerun()
    
    # 注销账号按钮（右下角）
    st.markdown("""
    <style>
    .danger-zone {
        margin-top: 2rem;
    }
    .danger-zone .stButton {
        display: flex;
        justify-content: flex-end;
    }
    .danger-zone .stButton > div {
        width: 30%;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="danger-zone">', unsafe_allow_html=True)
    st.subheader("⚠️ 危险操作")
    st.warning("注销账号后，你的所有发布商品和留言都将被删除，此操作不可撤销！")
    
    # 显示注销确认状态
    if not st.session_state.get("show_delete_account_confirm", False):
        cols = st.columns([2, 1])
        with cols[1]:
            if st.button("🗑️ 注销账号", type="secondary", use_container_width=True):
                st.session_state["show_delete_account_confirm"] = True
                st.rerun()
    else:
        cols = st.columns([2, 1])
        with cols[1]:
            st.error("⚠️ 确定要注销账号吗？")
            confirm_cols = st.columns(2)
            with confirm_cols[0]:
                if st.button("✅ 确认注销", key="confirm_delete_account", type="primary"):
                    if delete_user(user["id"]):
                        logout_user()
                        st.success("账号已注销")
                    else:
                        st.error("注销失败")
                    st.session_state["show_delete_account_confirm"] = False
                    st.rerun()
            with confirm_cols[1]:
                if st.button("❌ 取消", key="cancel_delete_account", type="secondary"):
                    st.session_state["show_delete_account_confirm"] = False
                    st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)


def render_item_card(item: dict) -> None:
    """渲染商品卡片"""
    # 获取发布者用户名
    user_id = item.get("user_id")
    if user_id:
        user = get_user_by_id(user_id)
        username = user["username"] if user else "未知用户"
        user_display = f"👤 {username}"
    else:
        user_display = "👤 匿名发布"
    
    # 使用 Streamlit 原生组件构建卡片
    with st.container():
        # 标题和价格
        col1, col2 = st.columns([4, 1])
        with col1:
            st.subheader(item['title'])
            st.markdown(f"{user_display} · {item['category']} · {item['created_at']}")
        with col2:
            st.markdown(f"<h2 style='color:#e74c3c;text-align:right;margin:0'>¥{item['price']:.2f}</h2>", unsafe_allow_html=True)
        
        # 描述
        st.markdown(item['description'])
        
        # 图片（使用 st.image 点击可放大）
        images = item.get("images", [])
        if images:
            display_images = images[:3]
            for img_base64 in display_images:
                st.image(f"data:image/jpeg;base64,{img_base64}", width=150)
            if len(images) > 3:
                st.caption(f"📷 共 {len(images)} 张图片")
        
        st.divider()


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
                    user_id = current_user["id"] if current_user else None
                    add_message(item_id, msg_name, msg_contact, msg_content, user_id)
                    st.success("✅ 留言已发送！卖家将尽快回复")
                    st.session_state[show_key] = False
                    st.rerun()


def render_user_messages(item: dict) -> None:
    """显示当前登录用户自己的留言"""
    current_user = st.session_state.get("current_user")
    if not current_user:
        return
    
    current_user_id = current_user["id"]
    msgs = item.get("messages", [])
    user_messages = [m for m in msgs if m.get("user_id") == current_user_id]
    
    if user_messages:
        st.caption(f"📩 我的留言")
        for m in user_messages:
            st.markdown(f"""
            <div style="background:#e3f2fd;border-radius:8px;padding:0.6rem 1rem;margin-bottom:0.5rem;border-left:3px solid #1a73e8;color:#333333">
                <div><b>我</b> <span class="meta">· {m['time']}</span></div>
                <div style="margin-top:0.3rem">{m['content']}</div>
            </div>
            """, unsafe_allow_html=True)


def render_public_messages(item: dict) -> None:
    """显示公开留言（所有人可见）"""
    msgs = item.get("messages", [])
    if msgs:
        st.caption(f"💬 共 {len(msgs)} 条留言")
        for m in msgs:
            st.markdown(f"""
            <div style="background:#fff8e1;border-radius:8px;padding:0.6rem 1rem;margin-bottom:0.5rem;border-left:3px solid #ffa000;color:#333333">
                <div><b>{m['name']}</b> <span class="meta">· {m['time']}</span></div>
                <div style="margin-top:0.3rem">{m['content']}</div>
            </div>
            """, unsafe_allow_html=True)


def render_admin_panel(item: dict, key_prefix: str = "") -> None:
    """渲染留言管理面板（含删除功能）"""
    iid = item["id"]
    show_key = f"show_admin_{iid}"
    pw_key = f"{key_prefix}pw_{iid}" if key_prefix else f"pw_{iid}"
    
    # 获取当前登录用户
    current_user = st.session_state.get("current_user")
    current_user_id = current_user["id"] if current_user else None
    
    # 判断是否为帖子所有者
    item_user_id = item.get("user_id")
    is_owner = current_user_id is not None and item_user_id == current_user_id
    
    if st.session_state.get(show_key, False):
        pw = item.get("admin_password", "")
        can_view = True
        
        # 如果是帖子所有者，直接可以查看
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
            
            # 图片上传
            st.subheader("📷 商品照片")
            uploaded_images = upload_images(max_images=5)
            
            col1, col2 = st.columns(2)
            with col1:
                price = st.number_input("价格 (¥) *", min_value=0.0, step=1.0, format="%.2f")
            with col2:
                category = st.selectbox("分类 *", ["电子产品", "教材书籍", "生活用品", "服饰", "其他"])
            contact = st.text_input("联系方式", value=default_contact, 
                                   placeholder="微信 / QQ / 手机号")
            st.caption("留言可见性")
            messages_visibility = st.radio(
                "留言可见性",
                options=["仅自己可见", "公开（所有人可见）"],
                index=0,
                format_func=lambda x: x,
                label_visibility="collapsed",
                horizontal=True
            )
            submitted = st.form_submit_button("发布", type="primary", use_container_width=True)

            if submitted:
                if not title.strip():
                    st.error("请填写商品名称")
                elif price <= 0:
                    st.error("价格必须大于 0")
                else:
                    visibility = "private" if messages_visibility == "仅自己可见" else "public"
                    add_item(title.strip(), desc.strip(), price, category,
                             contact.strip(), visibility, user_id, uploaded_images)
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
            cols = st.columns(3)
            with cols[0]:
                if st.button(fav_btn, key=f"fav_{iid}"):
                    toggle_favorite(iid)
                    st.rerun()
            with cols[1]:
                if st.button("💬 留言", key=f"msg_btn_{iid}"):
                    st.session_state[f"show_msg_{iid}"] = not st.session_state.get(f"show_msg_{iid}", False)
                    st.rerun()
            with cols[2]:
                st.empty()

            # 根据留言可见性设置显示留言
            visibility = item.get("messages_visibility", "private")
            current_user = st.session_state.get("current_user")
            current_user_id = current_user["id"] if current_user else None
            item_user_id = item.get("user_id")
            is_owner = current_user_id is not None and item_user_id == current_user_id
            
            if visibility == "public":
                # 公开：显示所有留言
                render_public_messages(item)
            else:
                # 仅自己可见：只有发布者能看到所有留言
                if is_owner:
                    # 发布者查看自己的商品，显示所有留言
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
                else:
                    # 非发布者看不到留言
                    pass
            
            # 留言表单
            render_message_form(iid)

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
            cols = st.columns(2)
            with cols[0]:
                if st.button("❤️ 取消收藏", key=f"unfav_{iid}"):
                    toggle_favorite(iid)
                    st.rerun()
            with cols[1]:
                if st.button("💬 留言", key=f"fav_msg_btn_{iid}"):
                    st.session_state[f"show_msg_{iid}"] = not st.session_state.get(f"show_msg_{iid}", False)
                    st.rerun()

            # 根据留言可见性设置显示留言
            visibility = item.get("messages_visibility", "private")
            current_user = st.session_state.get("current_user")
            current_user_id = current_user["id"] if current_user else None
            item_user_id = item.get("user_id")
            is_owner = current_user_id is not None and item_user_id == current_user_id
            
            if visibility == "public":
                # 公开：显示所有留言
                render_public_messages(item)
            else:
                # 仅自己可见：只有发布者能看到所有留言
                if is_owner:
                    # 发布者查看自己的商品，显示所有留言
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
                else:
                    # 非发布者看不到留言
                    pass
            
            # 留言表单（使用 fav_ 前缀区分）
            render_message_form(iid, "fav_")

# ─── 页面：用户中心 ─────────────────────────────────────
elif page == "用户中心":
    current_user = st.session_state.get("current_user")
    if current_user:
        render_user_info_panel()
    else:
        render_login_register_panel()