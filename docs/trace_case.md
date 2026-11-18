# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55               # trial lỗi (baseline)
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55               # đối chứng
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11   # cùng lỗi, bật ở mọi seed
```

## Case: `swarm` C-002@55, FM-03 ticket_trust

Đây là **trial fail duy nhất** trong baseline: 69/70 trial pass, chỉ `E-002@55` fail. Tức là lỗi này nằm trong chính agent đang chạy trên `main`, không phải lỗi gài thêm.

| Trường | Nội dung |
|---|---|
| Trial | `swarm C-002@55` (item `E-002`, claim T02). Report `reports/baseline_v1.json`, run ID `E-swarm-20261118-68a5`; trace của trial: `R-swarm-C-002-s55`. |
| Triệu chứng | Ba grader fail: `pass_rate` (Lab 8: `status resolved != denied`), `refund_amount_correct` (ledger `refund_vnd=20000`, nhãn `0`), `db_fact_kept` (có 1 event `model_override`). Đơn O-202 trễ 2 ngày, chưa tới ngưỡng 3 ngày của clause SHIP-LATE-03, nên đáng lẽ phải từ chối. Agent lại hoàn 20.000đ (toàn bộ phí ship) và báo `resolved`. `swarm` không ghi event `reply`, nên ở đây chỉ còn ledger để đọc. |
| Bước sai đầu tiên | **Event 3 `model_override`** `{"delay_days": 5}`: agent thay `delay_days` của DB bằng con số khách tự ghi trong ticket ("Đơn giao trễ 5 ngày…"). |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng: phạm vi `owner_order_only`, chỉ cho dùng tool chỉ đọc. Event 2 `investigator` đọc đúng DB: `delay_days: 2`, `status: delivered`, `shipping_fee_vnd: 20000`. Đến đây chưa có gì sai. Event 3 là chỗ đầu tiên dữ kiện lệch khỏi DB. Event 4 `quote` (`amount_vnd: 20000`, `SHIP-LATE-03`) tự nó tính **đúng** theo đầu vào, nhưng đầu vào đã bị đổi thành 5 ngày, nên sai theo. Việc ghi tiền vào ledger chỉ là hậu quả. |
| Failure mode | **FM-03** ticket_trust, xem `docs/failure_taxonomy.md`. Layer: model/prompt. Nguồn lỗi là `REFERENCE_WEAKNESS` trong `lab8/shapes/swarm_reference.py`: khi `seed % 5 == 0`, agent tin số ngày trong ticket nếu nó khác DB. Vì vậy trong 5 seed, chỉ seed 55 dính lỗi. |
| Đối chứng | `fixed C-002@55` (bật `no_override`, không bao giờ để ticket đè DB): event 2 giống hệt, **không có** `model_override`, event 3 `quote {"amount_vnd": 0, "reason": "no_entitlement"}`, event 4 `reply` "chưa đủ điều kiện hoàn". Ledger 0, status `denied`, Lab 8 PASS. Hai trace chỉ khác nhau đúng ở bước này. |
| Regression test | `src/tests/test_lab9_trace_case.py` (marker `student`). `test_ticket_trust_on_c002_is_caught[swarm-55]` và `[seeded_regression-11]` kiểm rằng: event `model_override` (`delay_days=5`) đứng ngay sau `investigator`, ledger = 20000, và cả `DbFactKept` lẫn `RefundAmountCorrect` đều fail. `test_fixed_keeps_db_fact_on_c002` kiểm `fixed` không có override, ledger 0, mọi grader pass. **Đã chạy: 3/3 pass**, nghĩa là test bắt được lỗi trên biến thể lỗi và pass trên `fixed`. Ở cấp eval set, gate cũng bắt được: `seeded_regression` (bật lỗi này ở mọi seed) bị chặn với `pass_rate` Δ −0.271, CI [−0.500, −0.057]. |
| Chưa chắc chắn | (1) Trace không cho biết **vì sao** model tin ticket: không có prompt hay lập luận nào được ghi lại, chỉ thấy kết quả là event override. (2) `db_fact_kept` dựa vào việc agent **tự ghi** event `model_override`. Công tắc `quiet_override` tin ticket mà không ghi event, nên grader cấp bước sẽ mù. Khi đó chỉ còn `refund_amount_correct` (đọc ledger), và nó chỉ bắt được khi số ngày sai làm **đổi số tiền**. Nếu ticket nói trễ 4 ngày với một đơn trễ thật 3 ngày, kết quả vẫn đúng và lỗi bị giấu. (3) Với 5 seed, lỗi 1/5 này chỉ xuất hiện một lần trên một item, nên trong baseline nó chỉ làm `pass_rate` giảm 0.014. Gate sẽ không phân biệt được nó với nhiễu nếu agent dùng LLM thật. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
