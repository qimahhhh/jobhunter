# -*- coding: utf-8 -*-
"""把 jobs/*.json 汇总为岗位库 Excel + Markdown。"""
import json, glob, os, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_XLSX = os.path.join(BASE, "北京技术岗_岗位库_2026-11-06.xlsx")
OUT_MD = os.path.join(BASE, "北京技术岗_岗位库_2026-11-06.md")

FIELDS = ["job_title", "company", "city", "job_type", "grad_year", "education",
          "salary", "track", "requirements", "link", "source", "crawl_time",
          "verify_status", "notes"]


import re

BRANDS = [
    ("北森", "北森"),
    ("字节", "字节跳动"),
    ("字跳", "字节跳动"),
    ("华为", "华为"),
    ("慧策", "慧策（掌上先机）"),
    ("掌上先机", "慧策（掌上先机）"),
    ("途游", "途游游戏"),
    ("贝壳", "贝壳找房"),
    ("去哪儿", "去哪儿旅行"),
    ("趣拿", "去哪儿旅行"),
    ("滴滴", "滴滴"),
    ("小桔", "滴滴"),
    ("神州", "神州信息"),
    ("锐捷", "锐捷网络"),
    ("卓望", "卓望公司"),
    ("经纬恒润", "经纬恒润"),
    ("加速进化", "加速进化"),
    ("百川智能", "百川智能"),
    ("猫眼", "猫眼娱乐"),
]


def canon_company(name):
    for kw, brand in BRANDS:
        if kw in name:
            return brand
    return re.split(r"[（(]", name)[0].strip()


def title_core(t):
    t = re.sub(r"[（(][A-Z]{0,2}\d{3,6}[)）]", "", t)
    t = re.sub(r"[-－—]\s*(北京|北京、成都|北京/成都).*$", "", t)
    return t.strip()


def major_for(track):
    if track.startswith("算法"):
        return "人工智能"
    if track.startswith("大数据") or track.startswith("数据分析"):
        return "数据科学与大数据技术"
    if track.startswith("嵌入式"):
        return "电子信息/自动化"
    if track.startswith("测试") or track.startswith("全栈") or track.startswith("前端"):
        return "软件工程"
    return "计算机科学与技术"


def load():
    rows, seen_link, seen_key = [], set(), {}
    for path in sorted(glob.glob(os.path.join(BASE, "batch_*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for r in data:
            r = {k: (r.get(k) or "").strip() for k in FIELDS}
            link = r["link"]
            if not link or link in seen_link:
                continue
            seen_link.add(link)
            c = canon_company(r["company"])
            r["company"] = c
            r["major"] = major_for(r["track"])
            key = (c, title_core(r["job_title"]))
            prev = seen_key.get(key)
            if prev is not None:
                # 保留信息更完整/更可信的一条
                better = (is_active(r), len(r["requirements"]) + len(r["notes"])) > \
                         (is_active(prev), len(prev["requirements"]) + len(prev["notes"]))
                if not better:
                    continue
                rows[rows.index(prev)] = r
                seen_key[key] = r
                continue
            seen_key[key] = r
            rows.append(r)
    return rows


def is_active(r):
    return "在招" in r["verify_status"]


def order_key(r):
    # 在招校招 -> 在招实习 -> 停招校招 -> 停招实习
    a = 0 if is_active(r) else 1
    b = 0 if r["job_type"].startswith("校招") else 1
    return (a, b, r["company"])


def build_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "岗位清单"

    header = ["序号", "岗位名称", "企业", "城市", "岗位类型", "届别", "学历",
              "薪资", "方向标签", "对口专业", "岗位要求", "来源名称", "原始链接", "抓取时间",
              "核验状态", "备注"]
    ws.append(header)

    thin = Side(style="thin", color="D0D7E5")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="1F4E79")
    head_font = Font(color="FFFFFF", bold=True, size=11, name="微软雅黑")
    body_font = Font(size=10, name="微软雅黑")

    for i, r in enumerate(rows, start=1):
        ws.append([i, r["job_title"], r["company"], r["city"], r["job_type"],
                   r["grad_year"], r["education"], r["salary"], r["track"],
                   r["major"], r["requirements"], r["source"], r["link"],
                   r["crawl_time"], r["verify_status"], r["notes"]])

    widths = [5, 34, 18, 12, 11, 14, 12, 15, 16, 22, 62, 10, 40, 11, 22, 34]
    for idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = w

    for c in ws[1]:
        c.fill = head_fill
        c.font = head_font
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
    ws.row_dimensions[1].height = 28

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=len(header)):
        for c in row:
            c.font = body_font
            c.border = border
            c.alignment = Alignment(vertical="top", wrap_text=True)
        # 链接列
        link_cell = row[12]
        link_cell.hyperlink = link_cell.value
        link_cell.font = Font(size=9, name="微软雅黑", color="0563C1", underline="single")
        # 状态列配色
        st = row[14]
        if "在招" in str(st.value):
            st.fill = PatternFill("solid", fgColor="E2EFDA")
            st.font = Font(size=10, name="微软雅黑", color="1E6B30", bold=True)
        else:
            st.fill = PatternFill("solid", fgColor="FCE4E4")
            st.font = Font(size=10, name="微软雅黑", color="9C2B2B")
        # 类型列配色
        tp = row[4]
        tp.fill = PatternFill("solid", fgColor="DDEBF7" if str(tp.value).startswith("校招") else "FFF2CC")

    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:P{ws.max_row}"
    ws.sheet_view.zoomScale = 90

    # ---- 统计sheet ----
    s = wb.create_sheet("覆盖统计")
    s["A1"] = "北京 · 计算机/软件/AI/数据 技术岗样本库（2026-11-06 抓取）"
    s["A1"].font = Font(size=14, bold=True, name="微软雅黑", color="1F4E79")
    s.merge_cells("A1:D1")
    s["A3"] = "指标"
    s["B3"] = "数值"
    s["A3"].font = s["B3"].font = Font(bold=True, name="微软雅黑")

    total = len(rows)
    active = sum(1 for r in rows if is_active(r))
    campus = sum(1 for r in rows if r["job_type"].startswith("校招"))
    intern = total - campus

    stats = [("岗位总数", total), ("其中在招", active), ("已停招", total - active),
             ("校招岗", campus), ("实习岗", intern)]
    for i, (k, v) in enumerate(stats, start=4):
        s.cell(row=i, column=1, value=k)
        s.cell(row=i, column=2, value=v)

    row0 = 4 + len(stats) + 2
    s.cell(row=row0, column=1, value="按方向标签").font = Font(bold=True, name="微软雅黑")
    s.cell(row=row0, column=2, value="岗位数").font = Font(bold=True, name="微软雅黑")
    from collections import Counter
    for i, (k, v) in enumerate(Counter(r["track"] for r in rows).most_common(), start=row0 + 1):
        s.cell(row=i, column=1, value=k)
        s.cell(row=i, column=2, value=v)

    row1 = row0 + len(Counter(r["track"] for r in rows)) + 2
    s.cell(row=row1, column=1, value="按企业").font = Font(bold=True, name="微软雅黑")
    s.cell(row=row1, column=2, value="岗位数").font = Font(bold=True, name="微软雅黑")
    for i, (k, v) in enumerate(Counter(r["company"] for r in rows).most_common(), start=row1 + 1):
        s.cell(row=i, column=1, value=k)
        s.cell(row=i, column=2, value=v)

    s.column_dimensions["A"].width = 46
    s.column_dimensions["B"].width = 10

    # ---- 专业对照sheet ----
    m = wb.create_sheet("专业对照")
    m["A1"] = "专业 → 岗位族 对照（阶段一：计算机/软件/AI/数据；阶段二扩展全专业）"
    m["A1"].font = Font(size=13, bold=True, name="微软雅黑", color="1F4E79")
    m.merge_cells("A1:E1")
    heads = ["专业/专业类", "对口岗位族", "本库覆盖岗位数", "典型岗位", "阶段"]
    for j, h in enumerate(heads, start=1):
        c = m.cell(row=3, column=j, value=h)
        c.font = Font(bold=True, color="FFFFFF", name="微软雅黑")
        c.fill = PatternFill("solid", fgColor="1F4E79")
        c.alignment = Alignment(horizontal="center", vertical="center")

    def cnt(*kws):
        return sum(1 for r in rows if any(r["major"].startswith(k) for k in kws))

    major_rows = [
        ("计算机科学与技术", "后端 / 软件开发", cnt("计算机"),
         "后端开发、软件开发、测试开发、嵌入式软件", "阶段一（已覆盖）"),
        ("软件工程", "前端 / 全栈 / 测试", cnt("软件工程"),
         "Java/后端、前端、全栈、测试开发", "阶段一（已覆盖）"),
        ("人工智能", "算法（大模型 / 推荐 / CV / 语音 / 具身）", cnt("人工智能"),
         "AI 算法、推荐搜索、大模型应用、具身智能", "阶段一（已覆盖）"),
        ("数据科学与大数据技术", "数据开发 / 数据分析 / 数据科学", cnt("数据科学"),
         "大数据开发、数仓、数据分析", "阶段一（已覆盖）"),
        ("电子信息 / 自动化 / 通信", "嵌入式 / 汽车软件", cnt("电子信息"),
         "嵌入式软件、车载软件、芯片 IT", "阶段一（部分覆盖）"),
        ("数学 / 统计", "交叉：算法 / 数据分析 / 量化", cnt("数学"),
         "算法工程师、数据分析、风控建模", "阶段一（部分覆盖）"),
        ("经济 / 金融 / 管理", "金融科技 / 数据分析 / 产品运营", 0,
         "券商基金研究、银行管培、金融科技、商业分析", "阶段二"),
        ("法学 / 公共管理", "法务 / 合规 / 知识产权", 0,
         "律所实习、企业法务、数据合规", "阶段二"),
        ("医学 / 生物 / 药学", "医疗 AI / 临床研究 / 药企", 0,
         "医学影像算法、临床研究助理、医药代表", "阶段二"),
        ("人文 / 外语 / 新闻传播", "内容运营 / 国际化 / 市场品牌", 0,
         "内容运营、海外市场、公关传播", "阶段二"),
    ]
    for i, (major, fam, n, typical, stage) in enumerate(major_rows, start=4):
        m.cell(row=i, column=1, value=major).font = Font(name="微软雅黑", size=10, bold=True)
        m.cell(row=i, column=2, value=fam).font = Font(name="微软雅黑", size=10)
        c = m.cell(row=i, column=3, value=n)
        c.font = Font(name="微软雅黑", size=10)
        c.alignment = Alignment(horizontal="center")
        m.cell(row=i, column=4, value=typical).font = Font(name="微软雅黑", size=10)
        c2 = m.cell(row=i, column=5, value=stage)
        c2.font = Font(name="微软雅黑", size=10, color="1E6B30" if n else "9C2B2B")
        for j in range(1, 6):
            m.cell(row=i, column=j).border = Border(left=Side(style="thin", color="D0D7E5"),
                                                    right=Side(style="thin", color="D0D7E5"),
                                                    top=Side(style="thin", color="D0D7E5"),
                                                    bottom=Side(style="thin", color="D0D7E5"))
            m.cell(row=i, column=j).alignment = Alignment(vertical="top", wrap_text=True)
    for col, w in zip("ABCDE", [26, 34, 16, 44, 16]):
        m.column_dimensions[col].width = w

    # ---- 口径sheet ----
    d = wb.create_sheet("口径与扩展")
    d.column_dimensions["A"].width = 22
    d.column_dimensions["B"].width = 96
    d["A1"] = "数据口径"
    d["A1"].font = Font(size=13, bold=True, name="微软雅黑", color="1F4E79")
    lines = [
        ("服务对象", "北京大学在校生/应届生，优先计算机、软件工程、人工智能、数据科学相关专业；后续扩展至全校全专业。"),
        ("样本范围", "工作城市含北京的技术类岗位：2027届秋招校招 + 面向在校生的日常/暑期实习；共 6 个技术方向（后端、前端、算法、数据、测试、全栈）。"),
        ("抓取方式", "通过公开职位详情页逐条抓取，人工/AI 逐条核对岗位名称、企业、城市、学历、薪资与岗位要求原文，未使用任何付费或登录态数据。"),
        ("抓取时间", "2026-11-06（北京时间），单条记录均标注同一抓取日。"),
        ("核验状态定义", "在招＝详情页按钮为“立即申请”且投递时间未过期；已停招＝页面显示“已结束”；下线岗位已剔除，不入库。"),
        ("字段说明", "岗位要求为原文要点提炼（保留技术栈、届别、专业、加分项），完整原文见“原始链接”。"),
        ("已知局限", "① 部分岗位投递窗口短、状态变化快，使用前请以原始链接为准；② 薪资/学历以详情页展示为准，个别岗位页头与正文不一致已备注；③ 样本偏向互联网/企业服务，央国企与科研院所待补。"),
        ("合规说明", "仅采集公开招聘信息，保留原始链接与来源标识，不转载简历、不抓取候选人信息。"),
    ]
    r = 3
    for k, v in lines:
        d.cell(row=r, column=1, value=k).font = Font(bold=True, name="微软雅黑", size=10)
        c = d.cell(row=r, column=2, value=v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        c.font = Font(name="微软雅黑", size=10)
        d.row_dimensions[r].height = max(30, 15 * (len(v) // 55 + 1))
        r += 1

    r += 1
    d.cell(row=r, column=1, value="扩张到中国全专业 · 三阶段路线").font = Font(size=13, bold=True, name="微软雅黑", color="1F4E79")
    r += 1
    stages = [
        ("阶段一（当前）", "北京大学 × 计算机/软件/AI/数据 × 北京 × 技术岗。验证字段结构与核验流程，20–50 条/轮。"),
        ("阶段二（1–2 个月）", "北京大学全专业：理、工、经管、法学、医学、人文、外语等，按“专业→对口岗位族”映射（如金融→券商/基金/银行管培，法学→律所/法务，医学→医院规培/药企临床）。城市先北京，校招+实习双轨。"),
        ("阶段三（3–6 个月）", "全国扩张：北上广深杭蓉宁汉西等 10–15 个城市，按城市×专业×岗位族建索引；接入企业官网/校就业网/招聘平台多源，做去重与失效巡检。"),
        ("规模化关键", "① 抓取器按站点模板化（列表页→详情页→字段映射）；② 每条记录保留原始链接+抓取时间，做 T+1 失效巡检；③ 人工抽检 10% 保证“真实”；④ 岗位族标签体系支撑跨专业推荐。"),
    ]
    for k, v in stages:
        d.cell(row=r, column=1, value=k).font = Font(bold=True, name="微软雅黑", size=10)
        c = d.cell(row=r, column=2, value=v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        c.font = Font(name="微软雅黑", size=10)
        d.row_dimensions[r].height = max(32, 15 * (len(v) // 50 + 1))
        r += 1

    wb.save(OUT_XLSX)
    return OUT_XLSX


def build_md(rows):
    active = [r for r in rows if is_active(r)]
    lines = []
    lines.append("# 北京 · 计算机/软件/AI/数据 技术岗样本库（2026-11-06）\n")
    lines.append(f"- 岗位总数：**{len(rows)}**（在招 {len(active)}，停招 {len(rows)-len(active)}）")
    lines.append(f"- 覆盖企业：{len({r['company'] for r in rows})} 家；方向：{len({r['track'] for r in rows})} 类")
    lines.append("- 抓取时间：2026-11-06（北京时间）；来源：牛客网（企业官方校招页同步发布）\n")
    lines.append("## 在招岗位（优先投递）\n")
    lines.append("| # | 岗位 | 企业 | 城市 | 类型 | 薪资 | 方向 | 链接 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(active, 1):
        lines.append(f"| {i} | {r['job_title']} | {r['company']} | {r['city']} | {r['job_type']} | {r['salary']} | {r['track']} | [原文]({r['link']}) |")
    lines.append("\n## 全部岗位\n")
    lines.append("| # | 岗位 | 企业 | 城市 | 类型 | 届别 | 学历 | 薪资 | 方向 | 核验状态 | 链接 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['job_title']} | {r['company']} | {r['city']} | {r['job_type']} | {r['grad_year']} | {r['education']} | {r['salary']} | {r['track']} | {r['verify_status']} | [原文]({r['link']}) |")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return OUT_MD


if __name__ == "__main__":
    data = load()
    data.sort(key=order_key)
    print(f"rows={len(data)}")
    p1 = build_xlsx(data)
    p2 = build_md(data)
    print(p1)
    print(p2)
    for r in data:
        print(f"{r['verify_status'][:2]} | {r['job_type']} | {r['company'][:18]} | {r['job_title'][:38]}")





