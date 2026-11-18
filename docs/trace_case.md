# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case đã điền

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11` (run `E-seeded_regression-20261118-d1f1`); đối chứng `fixed C-002@11` (run `E-fixed-20261118-d1f1`) |
| Triệu chứng | Lab 8 grader FAIL: `status resolved != denied`. Ledger ghi `refund_vnd=20000`, `refund_count=1`; nhãn yêu cầu `refund_vnd=0`, `refund_count=0`. Reply: "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." |
| Bước sai đầu tiên | Event **#3 `model_override`** với payload `{"delay_days": 5}` — agent lấy delay 5 ngày từ ticket để ghi đè fact DB (DB ghi 2 ngày), trước khi quote. |
| Vì sao là bước *đầu tiên* | Event #1 `handoff` và #2 `investigator.lookup_order` còn đúng (`visible=true`, `reason=ok`, order O-202 `delivered`). Sai bắt đầu từ #3; #4 `quote` chỉ là hệ quả (20.000đ, clause `SHIP-LATE-03`), #5 `refund_history` = 0, #6 `reply` báo số tiền. |
| Failure mode | **FM-03 `ticket_trust`** — tin ticket hơn dữ liệu DB có thẩm quyền (`docs/failure_taxonomy.md`). |
| Đối chứng | Trên `fixed C-002@11`: không có `model_override`; event #3 là `quote` với `amount_vnd=0`, `reason=no_entitlement`; reply nói đơn chưa đủ điều kiện; ledger 0, status `denied`. |
| Regression test | `src/tests/test_lab9_graders.py::test_override_event_breaks_db_fact` (`DbFactKept` bắt event `model_override`); item **E-002** (C-002) trong eval set v1 fail cả 5 seed trên `seeded_regression` và pass trên `fixed`; `TrialPass`/`RefundAmountCorrect` bắt ledger/status lệch nhãn. |
| Chưa chắc chắn | Trace chứng minh bước override và hậu quả ledger/reply, nhưng không chứng minh được vì sao agent chọn ticket thay vì DB (prompt/model); nhãn lấy từ matrix Lab 8, chưa có người thứ hai kiểm lại. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
