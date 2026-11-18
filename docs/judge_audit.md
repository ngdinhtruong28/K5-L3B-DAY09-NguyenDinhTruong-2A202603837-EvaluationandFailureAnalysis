# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Có | Dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không | Loại |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | Người | Judge chấp nhận thông báo hoàn tiền nhưng thiếu bằng chứng xác nhận giao dịch. |
| 2 | H-017 | PASS | FAIL | Người | Judge chấp nhận thông báo hoàn tiền 25.000đ dù thiếu bằng chứng giao dịch. |
| 3 | H-029 | PASS | FAIL | Người | Phản hồi chỉ yêu cầu khách hàng chờ, không cung cấp giải pháp hữu ích. |
| 4 | H-042 | FAIL | PASS | Judge | Judge đánh giá quá nghiêm khắc phản hồi có số tiền hoàn và thời gian nhận tiền cụ thể. |
| 5 | H-051 | FAIL | PASS | Judge | Judge không nhận diện được phản hồi thông báo hoàn tiền hợp lệ. |
| 6 | HL-015 | PASS | FAIL | Người | Judge chấp nhận thông báo hoàn tiền nhưng thiếu bằng chứng xác nhận. |
| 7 | HL-016 | PASS | FAIL | Người | Judge chấp nhận lời xin lỗi chung chung, không đưa ra hướng xử lý cụ thể. |
| 8 | HL-020 | PASS | FAIL | Người | Judge chấp nhận thông báo hoàn tiền thiếu bằng chứng giao dịch. |
| 9 | HL-028 | PASS | FAIL | Người | Judge đánh giá cao lời xin lỗi chung chung dù thiếu tính hữu ích. |
| 10 | HL-035 | PASS | FAIL | Người | Judge chấp nhận lời xin lỗi nhưng không đưa ra giải pháp xử lý vấn đề. |

## Kết luận
- **tone_ok: Được sử dụng (GO)**
  - Kappa = 0.757, đạt ngưỡng ≥ 0.6.
  - Precision = 0.857, đạt ngưỡng ≥ 0.8.
  - Recall = 0.800, đạt ngưỡng ≥ 0.7.
  - Ma trận nhầm lẫn: TP = 24, FP = 4, FN = 6, TN = 66.
  - Judge có mức độ đồng thuận đủ tốt với người đánh giá.

- **helpful: Bị loại (NO-GO)**
  - Kappa = 0.375, không đạt ngưỡng ≥ 0.6.
  - Precision = 1.000, đạt ngưỡng ≥ 0.8.
  - Recall = 0.300, không đạt ngưỡng ≥ 0.7.
  - Ma trận nhầm lẫn: TP = 9, FP = 0, FN = 21, TN = 70.
  - Có 21 trường hợp FAIL bị Judge đánh giá nhầm thành PASS.
  - Judge quá dễ dãi với các câu trả lời chỉ xin lỗi chung chung hoặc thông báo hoàn tiền nhưng thiếu bằng chứng xác nhận.

### Rủi ro còn lại

- Judge mới được kiểm thử trên dữ liệu replay đã công khai, chưa có tập held-out độc lập với nhãn do người đánh giá mới thực hiện.
- Kết quả có thể chưa phản ánh chính xác hiệu suất khi triển khai trên hội thoại thực tế.
- Tiêu chí helpful có nguy cơ bỏ sót các phản hồi không thực sự hữu ích do Recall thấp.
- Cần cải thiện rubric/prompt và đánh giá lại Judge trên dữ liệu mới trước khi triển khai.
