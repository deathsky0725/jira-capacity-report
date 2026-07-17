# Plan: ปรับปรุงความแม่นยำ Capacity/Velocity Report

> อัปเดตสถานะทุกครั้งที่ทำเสร็จ เพื่อให้กลับมาทำต่อได้ (checkbox ว่าง = ยังไม่ทำ, `[x]` = เสร็จ)
> วิธีรัน: `python3 sync.py` (ดึงข้อมูลใหม่) → `python3 build_report.py` → เปิด `report.html`

## บริบท

Pipeline: `sync.py` (Jira → jira.db) → `build_report.py` (คำนวณ + generate) → `report.html`
(template อยู่ที่ `report_template.html`, mapping status/field ต่อโปรเจกต์อยู่ที่ `config.json`, role+capacity รายคนอยู่ที่ `roles.json`)

ผลวิเคราะห์ที่เป็นเหตุผลของแผนนี้ (จากงานที่ปิดแล้ว 1,207 งาน ตั้งแต่ 2026-01-01):
- คนถืองานพร้อมกันเฉลี่ย 2–3.5 ใบ → เวลาจริงต่อใบบวมเป็น 2–3 เท่าของ point → อัตรา "ปิดตามประเมิน" ต่ำผิดจริง
- งานไม่มี point: Subtask 604/604, Bug 237/247 → คนทำบั๊ก/subtask ดู velocity ต่ำทั้งที่งานหนัก
- 24% ของงาน (294) ไม่เคยผ่านสถานะ dev เลย (To Do → Done) → วัดเวลาไม่ได้
- วันหยุดนักขัตฤกษ์ยังไม่ถูกหักจาก working days
- Weekend activity แค่ 1% → สมมติฐาน จ.–ศ. โอเค ไม่ต้องแก้

## Phases

### Phase 1: หักวันหยุดนักขัตฤกษ์ไทย `[x]`
- [x] เพิ่ม `holidays` (พ.ศ. 2569/ค.ศ. 2026 ทั้งปี) ลง config.json — แก้เพิ่ม/ลดได้ตามปฏิทินบริษัท
- [x] `workdays()` ใน build_report.py หักวันหยุดออก
- ผล: est-vs-actual ช่วงสงกรานต์/วันหยุดยาวไม่โดนบวมอีก

### Phase 2: WIP factor (multitasking) `[x]`
- [x] คำนวณ WIP เฉลี่ยรายคน = จำนวน card ที่ถือพร้อมกันเฉลี่ยต่อวันทำงาน (แยกฝั่ง dev: ช่วง เริ่ม dev→ส่งเทส / ฝั่ง tester: ช่วง รับของ→ปิด)
- [x] Estimate vs Actual: ความคาดหวัง = `point ÷ capacity × WIP` (แสดงคอลัมน์ WIP ให้เห็น)
- [x] Velocity tab: เพิ่มคอลัมน์ WIP เฉลี่ย
- ผล: คนที่โดนสลับงานเยอะไม่ถูกมองว่าช้า และ WIP สูงกลายเป็นสัญญาณให้หัวหน้าทีมจัดคิวงานใหม่

### Phase 3: Throughput + Imputed points (งานไม่มี point) `[x]`
- [x] คำนวณอัตรากลางของทีม: วันทำงานจริงต่อ 1 point (median จากงานที่มีทั้ง point และวันครบ) แยก dev/test
- [x] งานที่ไม่มี point แต่มีวันจริง → ประมาณ point ให้ = วันจริง ÷ อัตรากลาง (แสดงด้วย `~` และแถบสีอ่อน)
- [x] Velocity tab: แสดงทั้ง velocity จาก point จริง และ velocity รวมค่าประมาณ (ใช้ค่ารวมในการเทียบ over/under เพราะแฟร์กับคนทำบั๊ก)
- ข้อควรระวัง (เขียนแจ้งใน report แล้ว): imputed point วัด "เวลาที่ใช้" ไม่ใช่ "ผลงาน" — ใช้ดู workload ไม่ใช่จับผิดความเร็ว

### Phase 4: First-pass yield / คุณภาพงาน `[x]`
- [x] รายคนฝั่ง dev: % งานผ่าน QA รอบเดียว (ไม่โดน RETEST FAILED) — คู่กับ velocity เพื่อไม่ให้คนเร็วแต่งานตีกลับดูเป็น over-performer
- [x] รายคนฝั่ง tester: จำนวน defect ที่จับได้ (การจับ defect คือผลงานของ tester)

### Phase 5: Hygiene score (ความน่าเชื่อถือของข้อมูล) `[x]`
- [x] รายโปรเจกต์: % งานที่ flow ผ่านสถานะ dev จริง (ไม่กระโดด To Do→Done), % มี point, % ระบุ tester ได้
- [x] รายคน: % งานของตัวเองที่ status flow ครบ → ใช้เป็น KPI วินัยการลาก card

### Phase 6: นาฬิกา tester เริ่มที่เทสจริง + คิวรอ QA `[x]`
- [x] เพิ่ม `test_active` (สถานะกำลังเทสจริง) ต่อโปรเจกต์ใน config.json — วันจริง tester = เริ่มเทสจริง → ปิด (fallback เป็น Ready to test ถ้าโปรเจกต์ไม่มีสถานะเทสแยก)
- [x] คิวรอ = Ready to test → เริ่มเทสจริง แสดงราย issue ใน drill down และเป็นกราฟ trend รายสปรินต์ในหน้าภาพรวม (median, เฉพาะ sprint ที่มี ≥3 งาน)
- ผล: อัตรากลาง test ลดจาก 10 → 6.7 วัน/point, on-time ฝั่ง tester ขึ้น (เช่น Kornpharich 4%→52%) และเห็นคอขวด: FUN Sprint 46 คิว median 4 วัน

### Phase 7: Estimation bias ของทีม `[x]`
- [x] Histogram การกระจาย "เวลาจริง ÷ เวลาที่คาด (หลังปรับ capacity+WIP)" ใน tab Estimate vs Actual แยก Dev/Tester พร้อม median และคำแปลผลอัตโนมัติ
- ผล: Dev median 0.9× = การประเมินฝั่ง dev แม่นอยู่แล้ว · Tester median 2.1× = testing point ถูกตั้งต่ำกว่าจริงอย่างเป็นระบบ ~2 เท่า → ควรแก้ที่ planning ไม่ใช่รายคน

### Phase 8: Tab Insight + สัดส่วนประเภทงานรายคน `[x]`
- [x] Tab "Insight" — วิเคราะห์อัตโนมัติจากข้อมูลชุดปัจจุบัน (ตาม filter): estimation bias, คอขวดคิวเทส, context switching (WIP≥3), งานไม่มี point, hygiene ต่ำ, first-pass ต่ำ, สรุป over/under — เกณฑ์ทั้งหมด document ไว้ในหน้าวิธีคิด
- [x] การ์ด "สัดส่วนประเภทงานที่ปิด" (Story/Task/Bug/Subtask/Incident stacked bar รายคน) ใน tab Velocity
- [x] เติมวิธีคิดของ Phase 7 (bias) + Insight + type mix ลงหน้า "คุณภาพข้อมูล & วิธีคิด"

> **กติกา:** ทุกครั้งที่เพิ่ม logic/วิธีคิดใหม่ ต้องเขียนอธิบายในหน้า "คุณภาพข้อมูล & วิธีคิด" ด้วยเสมอ และถ้าได้ insight ใหม่ให้พิจารณาเพิ่มเป็นกฎอัตโนมัติใน tab Insight

### Phase 9: Carry-over rate รายสปรินต์ `[x]`
- [x] นิยาม: งาน carry-over = เริ่ม dev ก่อนวันเปิดของ sprint ที่ปิดงาน · กราฟ trend ในหน้าภาพรวม (sprint ที่วัดได้ ≥5 งาน) + ตัวเลขใน Drill down ราย sprint + กฎ Insight (>50% = เตือน planning)
- ผลปัจจุบัน: ทุก sprint อยู่ช่วง 0–50% ไม่มี sprint เกินเกณฑ์เตือน (สูงสุด FO Sprint 8 = 36%, IIC Sprint 6 = 50% พอดีเกณฑ์)

### Phase 10: หักวันลารายคน `[x]`
- [x] สร้าง `leaves.json` (ชื่อ → list วันที่ลาแบบ ISO) — build_report.py หักวันลาของเจ้าของงานออกจาก "วันจริง" อัตโนมัติ (ฝั่ง dev หักของ devOwner, ฝั่ง test หักของ tester คนแรก)
- [x] **สูตรเฉลี่ย (availability)** ตามที่ผู้ใช้กำหนด: ทุกคนมีลาพักร้อน 10 วัน/ปี ใช้หมดแน่ → availability = (242−10)÷242 = **95.9%** → "วันที่คาด" ทุกงานหารด้วยค่านี้ (ยืด ~4.3%) · ตั้งค่าที่ `annual_leave_days` ใน config.json
- [x] กันหักซ้ำซ้อน: คนที่มีวันลาจริงใน leaves.json จะไม่ถูกคูณสูตรเฉลี่ย (ข้อมูลจริง override) — เติมข้อมูลจริงเมื่อไหร่ก็แม่นขึ้นทันที

### Phase 11: Role "other" — แยกคนที่ไม่ใช่ dev/tester ออกจากค่าเฉลี่ย `[x]`
- [x] roles.json รองรับ `{"role":"other","label":"PO"}` — DevOps (Varut, Konthanat), TechDirector (Jakkrit), BA (pongsatorn whay), PO (Chalita, Waramporn)
- [x] คนกลุ่มนี้ถูกตัดออกจากตาราง/ค่าเฉลี่ย Velocity, Estimate, กฎ Insight (ยังเห็นใน Drill down ราย sprint พร้อม label)
- Impact หลัง recalculate: Dev 27→22 คน avg 6.76→7.07 (+4.6%) · Tester 10→9 คน avg 2.33→2.47 (+6%) · over/under ไม่มีใครสลับฝั่งจากการเปลี่ยนนี้

### Phase 12: Tab "Defect & Retest" `[x]`
- [x] วิธีจับ: defect = transition เข้าสถานะ fail (RETEST FAILED/TEST FAILED/Retest Failed/Failed ตามโปรเจกต์) · dev เจ้าของงาน = devOwner · tester ที่จับ = คนที่กด transition (จาก changelog) · ฐาน = งานที่เข้ามือเทสจริงในโปรเจกต์ที่มีสถานะ fail (FUN, IIC, WL, VFM)
- [x] แสดง: tiles ภาพรวม (base/% ตีกลับ/รอบรวม/งานเรื้อรัง ≥2 รอบ) · ตาราง % ตีกลับราย dev (ขั้นต่ำส่งเทส 3 งาน, คลิก drill down ราย issue) · ตาราง defect ที่จับได้ราย tester · trend % ตีกลับรายสปรินต์
- ผลปัจจุบัน: ฐาน 411 งาน โดนตีกลับ 4% (15 งาน, 22 รอบ) · เรื้อรัง ≥2 รอบมี 3 งาน · % สูงสุดราย dev คือ Sarawut 20% (2/10) · tester ที่จับเยอะสุดคือ Patiharn 11 รอบ/6 งาน

### Phase 13: เตรียมขึ้น git / ส่งต่อทีม `[x]`
- [x] README.md — เริ่มด้วย prompt สำหรับสั่ง Claude ต่อ Jira ของแต่ละคนหลัง pull, วิธี setup เอง, คำอธิบาย tab/config, ข้อกำหนดความปลอดภัย
- [x] .gitignore — กัน .env, jira.db, report.html, backlog*.{csv,json}, leaves.json (ข้อมูล internal/ส่วนบุคคลทั้งหมด)
- [x] .env.example — template credential (แต่ละคนใช้ token ของตัวเอง)
- [x] Security fix: sync.py/fetch_backlog.py อ่าน .env จากในโฟลเดอร์ก่อน (fallback โฟลเดอร์แม่) พร้อม error message แนะนำวิธี setup — คน clone repo ไปที่อื่นใช้ได้ทันที
- หมายเหตุ: repo นี้ internal เท่านั้น — roles.json/Plan.md มีชื่อพนักงานจริง ถ้าจะ public ต้องล้างก่อน

## Backlog (ยังไม่ทำ — คุยกันก่อน)

- (ว่าง — แผนหลักครบทุก phase แล้ว รอเพียงข้อมูลวันลาจริงมาเติม leaves.json ใน Phase 10)

## วันหยุดที่ใช้ (2026)

1 ม.ค., 2 ม.ค., 3 มี.ค. (มาฆบูชา), 6 เม.ย. (จักรี), 13–15 เม.ย. (สงกรานต์), 1 พ.ค. (แรงงาน), 4 พ.ค. (ฉัตรมงคล), 1 มิ.ย. (ชดเชยวิสาขบูชา 31 พ.ค.), 3 มิ.ย. (วันเฉลิมฯ พระราชินี), 28 ก.ค. (วันเฉลิมฯ ร.10), 29 ก.ค. (อาสาฬหบูชา), 12 ส.ค. (วันแม่), 13 ต.ค. (วันนวมินทรมหาราช), 23 ต.ค. (ปิยมหาราช), 7 ธ.ค. (ชดเชยวันพ่อ 5 ธ.ค.), 10 ธ.ค. (รัฐธรรมนูญ), 31 ธ.ค.
