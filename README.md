# Capacity & Velocity Report — Official Jira

Dashboard วัด capacity / velocity / คุณภาพงาน ของทุกทีมจาก official Jira ขององค์กร
ผลลัพธ์เป็น **`report.html` ไฟล์เดียว** เปิดได้ทุกเครื่องด้วย browser ไม่ต้องติดตั้งอะไร ส่งต่อให้ใครก็ได้

> ⚠️ **ข้อมูลทุกไฟล์ที่ดึงมา (jira.db, report.html) เป็น internal use only — ห้าม commit ขึ้น git** (`.gitignore` กันไว้ให้แล้ว)

## 🚀 เริ่มใช้ครั้งแรก (หลัง clone/pull)

วิธีที่ง่ายที่สุด: เปิด **Claude Code** ในโฟลเดอร์นี้ แล้วสั่งด้วย prompt ประมาณนี้

```
ช่วย setup โปรเจกต์ Jira report ในโฟลเดอร์นี้ให้หน่อย:
1. สร้างไฟล์ .env จาก .env.example — Jira email ของฉันคือ <อีเมลที่ใช้ login official Jira ของคุณ>
   ส่วน API token เดี๋ยวฉันสร้างจาก https://id.atlassian.com/manage-profile/security/api-tokens แล้วส่งให้
2. ทดสอบว่าต่อ Jira ได้ (ลอง call /rest/api/3/myself)
3. รัน python3 sync.py เพื่อดึงข้อมูล แล้วรัน python3 build_report.py
4. เปิด report.html ให้ดูหน่อย
```

Claude จะพาทำจนจบ — ตั้งแต่สร้าง `.env`, ตรวจการเชื่อมต่อ, ดึงข้อมูล, จนได้ report

### Setup เอง (ไม่ใช้ Claude)

```bash
cp .env.example .env        # แล้วแก้ email + token ของตัวเองในไฟล์
python3 sync.py             # ดึง issues + changelog ทุกโปรเจกต์ → jira.db (~2-3 นาที)
python3 build_report.py     # คำนวณ + สร้าง report.html
open report.html
```

ต้องมีแค่ **Python 3.9+** (ใช้ standard library ล้วน ไม่ต้อง pip install)

## 🔁 การอัปเดตข้อมูลรอบถัดไป

```bash
python3 sync.py && python3 build_report.py
```

## 📊 มีอะไรใน report

| Tab | เนื้อหา |
|---|---|
| ภาพรวม | points ที่ปิดรายสปรินต์ · คิวรอเข้าเทส · carry-over rate |
| Velocity รายคน | เทียบค่าเฉลี่ยทีมแบบ normalize (capacity/WIP) · over/under · สัดส่วนประเภทงาน |
| Drill down ราย Sprint | ใครทำอะไรบ้างในแต่ละ sprint คลิกดูราย issue ได้ |
| Estimate vs Actual | ประเมินไว้กี่ point ทำจริงกี่วัน (1 point = 1 วันทำงาน) + estimation bias ของทีม |
| Defect & Retest | อัตราโดนตีกลับราย dev · defect ที่จับได้ราย tester · trend รายสปรินต์ |
| Insight | ระบบวิเคราะห์อัตโนมัติ ชี้จุดควรแก้พร้อมข้อเสนอ |
| คุณภาพข้อมูล & วิธีคิด | **สูตรและนิยามทุกตัวอยู่ที่นี่** — อ่านก่อนตีความตัวเลข |

## ⚙️ ไฟล์ config (แก้แล้วรัน build_report.py ใหม่)

| ไฟล์ | ใช้ทำอะไร | ขึ้น git? |
|---|---|---|
| `config.json` | ช่วงเวลา, วันหยุด, mapping status/field ต่อโปรเจกต์, วันลาพักร้อน/ปี | ✅ |
| `roles.json` | role รายคน: `"dev"` / `"tester"` / `{"role":"dev","label":"PE","capacity":0.5}` / `{"role":"other","label":"PO"}` (other = ไม่นับในค่าเฉลี่ย) | ✅ |
| `leaves.json` | วันลาจริงรายคน (สร้าง template อัตโนมัติเมื่อรันครั้งแรก) | ❌ ข้อมูลส่วนบุคคล |
| `.env` | credential ส่วนตัวของแต่ละคน | ❌ เด็ดขาด |

โครงสร้าง pipeline: `sync.py` (Jira API → `jira.db`) → `build_report.py` (คำนวณ + ฝัง data ลง `report_template.html`) → `report.html`

ประวัติการพัฒนา + แผนที่เหลืออยู่: ดู [Plan.md](Plan.md)

## 🔐 ความปลอดภัย

- **API token เป็นของส่วนตัว** — แต่ละคนสร้างของตัวเอง ห้ามแชร์ ห้ามวางในแชท/เอกสาร และ revoke ทันทีเมื่อเลิกใช้ (ที่ https://id.atlassian.com/manage-profile/security/api-tokens)
- token เข้าถึง Jira ได้เท่าสิทธิ์บัญชีของเจ้าของ token — report จะเห็นเฉพาะโปรเจกต์ที่คนรันมีสิทธิ์เห็น
- ไฟล์ที่ `.gitignore` กันไว้ (`jira.db`, `report.html`, `backlog*.{csv,json}`, `leaves.json`, `.env`) ห้าม force add ขึ้น git
- repo นี้ออกแบบมาสำหรับ **internal team เท่านั้น** — `roles.json` และ `Plan.md` มีชื่อพนักงานจริง ถ้าวันหนึ่งจะเปิด public ต้องล้างไฟล์เหล่านี้ก่อน
