"""
校园二手交易平台 - Streamlit 单文件应用
功能：发布闲置、浏览/搜索商品、收藏管理、JSON 持久化
"""
import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

# ─── 数据层 ─────────────────────────────────────────────
DATA_FILE = Path("data.json")

DEFAULT_DATA = {"items": [], "next_id": 1}


def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_DATA.copy()


def save_data(data: dict) -> None:
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_all_items() -> list:
    return load_data().get("items", [])


def add_item(title: str, desc: str, price: float, category: str,
             contact: str, admin_password: str = "") -> None:
    data = load_data()
    item = {
        "id": data["next_id"],
        "title": title,
        "description": desc,
        "price": price,
        "category": category,
        "contact": contact,
        "admin_password": admin_password,
        "messages": [],  # 每条消息: {name, contact, content, time}
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data["items"].insert(0, item)
    data["next_id"] += 1
    save_data(data)


def add_message(item_id: int, name: str, contact: str, content: str) -> None:
    data = load_data()
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


def toggle_favorite(item_id: int) -> None:
    fav = st.session_state.favorites
    if item_id in fav:
        fav.remove(item_id)
    else:
        fav.add(item_id)


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
page = st.sidebar.radio("导航", ["浏览商品", "发布闲置", "我的收藏"])

# ─── 页面：发布闲置 ─────────────────────────────────────
if page == "发布闲置":
    st.header("📤 发布闲置")
    with st.form("publish_form", clear_on_submit=True):
        title = st.text_input("商品名称 *", max_chars=50)
        desc = st.text_area("商品描述", max_chars=500, height=100)
        col1, col2 = st.columns(2)
        with col1:
            price = st.number_input("价格 (¥) *", min_value=0.0, step=1.0, format="%.2f")
        with col2:
            category = st.selectbox("分类 *", ["电子产品", "教材书籍", "生活用品", "服饰", "其他"])
        contact = st.text_input("联系方式", placeholder="微信 / QQ / 手机号")
        admin_password = st.text_input("管理密码（查看留言时用）", type="password",
                                       placeholder="建议留空，留空则留言公开")
        submitted = st.form_submit_button("发布", type="primary", use_container_width=True)

        if submitted:
            if not title.strip():
                st.error("请填写商品名称")
            elif price <= 0:
                st.error("价格必须大于 0")
            else:
                add_item(title.strip(), desc.strip(), price, category,
                         contact.strip(), admin_password.strip())
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

            # ── 留言表单 ──
            if st.session_state.get(f"show_msg_{iid}", False):
                with st.form(key=f"msg_form_{iid}", clear_on_submit=True):
                    st.caption("💬 给卖家留言")
                    mc1, mc2 = st.columns(2)
                    with mc1:
                        msg_name = st.text_input("你的昵称", placeholder="可选")
                    with mc2:
                        msg_contact = st.text_input("你的联系方式", placeholder="微信 / QQ")
                    msg_content = st.text_area("留言内容", height=80, max_chars=300)
                    if st.form_submit_button("发送留言", type="primary"):
                        if not msg_content.strip():
                            st.error("请填写留言内容")
                        else:
                            add_message(iid, msg_name, msg_contact, msg_content)
                            st.success("✅ 留言已发送！卖家将尽快回复")
                            st.session_state[f"show_msg_{iid}"] = False
                            st.rerun()

            # ── 留言管理（卖家查看）──
            if st.session_state.get(f"show_admin_{iid}", False):
                pw = item.get("admin_password", "")
                can_view = True
                if pw:
                    entered = st.text_input("输入管理密码查看留言", type="password",
                                            key=f"pw_{iid}")
                    if entered != pw:
                        can_view = False
                        if entered:
                            st.error("密码错误")
                if can_view:
                    # 显示卖家联系方式
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

            # ── 留言表单 ──
            if st.session_state.get(f"show_msg_{iid}", False):
                with st.form(key=f"fav_msg_form_{iid}", clear_on_submit=True):
                    st.caption("💬 给卖家留言")
                    mc1, mc2 = st.columns(2)
                    with mc1:
                        msg_name = st.text_input("你的昵称", placeholder="可选", key=f"fn_{iid}")
                    with mc2:
                        msg_contact = st.text_input("你的联系方式", placeholder="微信 / QQ", key=f"fc_{iid}")
                    msg_content = st.text_area("留言内容", height=80, max_chars=300, key=f"fm_{iid}")
                    if st.form_submit_button("发送留言", type="primary"):
                        if not msg_content.strip():
                            st.error("请填写留言内容")
                        else:
                            add_message(iid, msg_name, msg_contact, msg_content)
                            st.success("✅ 留言已发送！")
                            st.session_state[f"show_msg_{iid}"] = False
                            st.rerun()

            # ── 留言管理 ──
            if st.session_state.get(f"show_admin_{iid}", False):
                pw = item.get("admin_password", "")
                can_view = True
                if pw:
                    entered = st.text_input("输入管理密码查看留言", type="password", key=f"fpw_{iid}")
                    if entered != pw:
                        can_view = False
                        if entered:
                            st.error("密码错误")
                if can_view:
                    # 显示卖家联系方式
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
                            <div style="background:#fff8e1;border-radius:8px;padding:0.6rem 1rem;margin-bottom:0.5rem;border-left:3px solid #ffa000">
                                <div><b>{m['name']}</b> <span class="meta">({m.get('contact','')})  · {m['time']}</span></div>
                                <div style="margin-top:0.3rem">{m['content']}</div>
                            </div>
                            """, unsafe_allow_html=True)