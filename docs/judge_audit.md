# Judge audit

Chạy (trong `src/`): `python -m lab9.judge --csv <file> --audit 5`

Judge được coi là một bộ phân loại, với **FAIL là lớp dương** (việc của judge là tìm ra câu trả lời lỗi). Ngưỡng tối thiểu (FLOORS): κ ≥ 0.6, P ≥ 0.8, R ≥ 0.7. Nếu κ không xác định thì tính là FAIL.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** | **dùng**, nhưng chỉ làm metric không chặn (non-blocking) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** (κ và R dưới sàn) | **loại** |

Ma trận nhầm lẫn:

| | tp | fp | fn | tn | Tỉ lệ FAIL quan sát → sau hiệu chỉnh Rogan-Gladen |
|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 → 0.30 (nhãn người: 30/100 = 0.30) |
| helpful | 9 | 0 | 21 | 70 | 0.09 → 0.30 (nhãn người: 30/100 = 0.30) |

## ≥5 case audit thủ công

### tone_ok: đủ 10 ca bất đồng

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | **Người** | Xưng "em" và dùng "nha" quá suồng sã với khách đang khiếu nại. Judge nhầm suồng sã là thân thiện. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | **Người** | Gọi khách là "bạn" sai ngôi xưng hô. Lỗi giống ca 1. |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | **Người** | Giọng ra lệnh. Judge chỉ nhìn thấy từ lịch sự ở đầu câu ("Dạ, vui lòng"). |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người** | Câu ngắn nhưng đủ ý và lễ phép. Judge phạt chỉ vì thiếu lời xin lỗi, tức là rubric đang đòi xin lỗi trong mọi trường hợp. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | **Người** | Quy định CS của LogiX cho phép dùng từ "refund". Judge phạt từ tiếng Anh dù quy định không cấm. |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | **Người**, nhưng đây không phải lỗi giọng điệu | Lời hứa "sẽ hoàn thêm" không có trong kết quả của hệ thống. Đây là lỗi **nội dung** (gần FM-08), phải chấm bằng code so với ledger, không giao cho judge tone. |
| 7 | H-070 "…đã hoàn 90.000đ… ạ 😂😂" | PASS | FAIL | **Người** | Emoji cười không hợp với ngữ cảnh khiếu nại. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Người gán nhãn đọc nhầm ticket nên nhãn người sai. Cần **sửa nhãn thành FAIL**. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | **Người** | "Dạ" bị lặp do lỗi gõ. Đây là lỗi trình bày, không làm sai giọng điệu, nên không đáng FAIL tone. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ… xin loi vi su bat tien." | PASS | FAIL | **Người** | Câu bị mất dấu tiếng Việt, đọc không chuyên nghiệp. Judge không nhận ra. |

Nếu sửa nhãn H-081: tp = 25, fp = 3, fn = 6, tn = 66, P = 0.893, R = 0.806, κ = 0.784. Judge tone vẫn đạt sàn và còn tốt hơn một chút. Kết luận cho tone_ok không đổi.

### helpful: 21 ca judge bỏ lọt (FAIL→PASS), nhóm theo nguyên nhân

| # | Case (nhóm) | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 11 | HL-015, 020, 062, 087, 100 (5 ca): câu ngắn "Dạ, LogiX đã hoàn X đ…" | PASS | FAIL | **Người** | Số tiền trong câu trả lời **khác ledger** (ví dụ HL-015 nói 55.000đ nhưng ledger ghi 40.000đ). Judge chỉ đọc câu trả lời, không thấy ledger, nên **không thể** bắt được lỗi này. |
| 12 | HL-016, 028, 035, 041, 043, 053, 058, 070, 072, 074, 090, 096, 098 (13 ca): xin lỗi dài, lặp lại, có số tiền ở giữa | PASS | FAIL | **Người** | Số tiền cũng sai so với ledger, lại bị bọc trong lời xin lỗi dài dòng. Judge thiên vị câu dài và lễ phép (verbosity bias). |
| 13 | HL-047, 091, 097 (3 ca): "Ok bạn, đơn O-xxx xử lý rồi nhé." | PASS | FAIL | **Người** | Câu không nói kết quả xử lý, số tiền hay thời gian. Judge vẫn cho qua. |

Judge helpful chỉ bắt được những câu **rõ ràng vô ích** (9 tp, ví dụ "Bạn gửi lại thông tin đi.", "Đơn O-909 không được hoàn."). Nó không bao giờ báo nhầm (fp = 0), nên P = 1.0, nhưng P cao ở đây không có nghĩa là judge tốt.

### Sửa rubric

- **tone_ok:**
  1. Thêm tiêu chí xưng hô: phải dùng "anh/chị" và "LogiX". Xưng "em", gọi khách "bạn", dùng "nha/nhé" hay emoji đều tính là FAIL.
  2. Giọng ra lệnh tính là FAIL, kể cả khi câu mở đầu bằng "Dạ, vui lòng".
  3. Câu tiếng Việt mất dấu tính là FAIL.
  4. **Bỏ** yêu cầu bắt buộc phải xin lỗi. Câu ngắn mà đủ ý và lễ phép vẫn là PASS.
  5. Cho phép các thuật ngữ nằm trong whitelist CS (ví dụ "refund").
  6. Lỗi gõ lặp từ không tính là lỗi tone.
  7. Nói rõ trong rubric rằng **tone không chấm nội dung hay số tiền**: lời hứa ngoài hệ thống (H-063) để cho grader code xử lý.
- **helpful:** không sửa rubric để cứu judge này. Phần lớn lỗi của nó (18/21) là sai số tiền so với ledger, thứ judge không có dữ liệu để kiểm tra. Theo quy tắc của lab, tiền luôn chấm bằng code: dùng `RefundAmountCorrect` cho ledger, và metric FM-08 (misreport) để so số tiền trong câu trả lời với ledger. Phần "câu trả lời mơ hồ" (ca 13), nếu cần, chuyển thành một judge hẹp mới (ví dụ: câu trả lời có nêu kết quả, số tiền và thời gian không) rồi hiệu chỉnh lại từ đầu.

## Kết luận

- **Tiêu chí bị loại: `helpful`.** Ma trận nhầm lẫn là tp = 9, fp = 0, fn = 21, tn = 70, nên R = 0.30 và κ = 0.375, cả hai đều dưới sàn.
  - Judge này bỏ lọt **21/30** câu trả lời tệ và làm tỉ lệ lỗi trông như chỉ 9% trong khi thực tế là 30%. Nếu dùng làm gate, nó sẽ cho merge đúng những bản agent báo sai số tiền, tức là loại lỗi nguy hiểm nhất.
  - Hiệu chỉnh Rogan-Gladen (0.09 → 0.30) không cứu được judge này. Rogan-Gladen giả định judge sai **ngẫu nhiên, đều trên mọi item**. Ở đây judge sai **có hệ thống** trên một nhóm cụ thể (sai số tiền, câu dài). Chỉ cần nhóm đó tăng lên trong một PR, tỉ lệ sau hiệu chỉnh sẽ lệch, mà gate không biết.
- **Tiêu chí được dùng: `tone_ok`** (κ = 0.757, P = 0.857, R = 0.8), nhưng chỉ ở mức **non-blocking**, kèm báo cáo tỉ lệ đã hiệu chỉnh.
  - Judge vẫn bỏ lọt 6/30 lỗi tone, chủ yếu là lỗi xưng hô.
  - Trong 4 lần báo nhầm, 3 lần do rubric quá khắt khe (đòi xin lỗi, cấm từ tiếng Anh, phạt lỗi gõ) và 1 lần do nhãn người sai.
- **Rủi ro còn lại:**
  - Judge mới chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí). Sau khi sửa rubric, cần một bộ nhãn người **mới, held-out** để đo lại; không đo lại trên chính 100 dòng đã dùng để sửa rubric.
  - n = 100 nhỏ, nên κ và R có khoảng tin cậy rộng. R = 0.8 của tone tính trên 30 ca FAIL, chỉ cần thêm 3 ca bỏ lọt là xuống 0.7.
  - Nhãn người cũng có lỗi (H-081). Nên có hai người gán nhãn độc lập và đo κ giữa hai người để biết giới hạn trên của judge.
