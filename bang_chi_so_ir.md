# Chỉ số IR/QA của khối truy hồi

Đo ngày 15/09/2026 trên 97 câu hỏi có nhãn nguồn, kho 25761 vector, truy hồi sâu 24 chunk (4 chunk đi vào prompt).

| Nhóm câu hỏi | Số câu | MRR | Hit@1 | Hit@3 | Hit@5 | Hit@10 | nDCG@10 |
|---|---|---|---|---|---|---|---|
| bang_excel | 8 | 0.713 | 62.5% | 62.5% | 100.0% | 100.0% | 0.712 |
| chinh_sach_pdf | 50 | 0.890 | 88.0% | 90.0% | 90.0% | 90.0% | 0.893 |
| tai_lieu_docx | 14 | 0.821 | 71.4% | 92.9% | 92.9% | 92.9% | 0.794 |
| trinh_chieu | 14 | 0.631 | 42.9% | 85.7% | 85.7% | 85.7% | 0.655 |
| van_ban_doc | 6 | 0.889 | 83.3% | 100.0% | 100.0% | 100.0% | 0.917 |
| video | 5 | 0.467 | 40.0% | 60.0% | 60.0% | 60.0% | 0.423 |
| **Toàn bộ** | 97 | 0.806 | 74.2% | 86.6% | 89.7% | 89.7% | 0.806 |

MRR@10 = 0.806, khoảng tin cậy 95% (bootstrap) 0.735 – 0.875. Trong cửa sổ 4 chunk thực sự đi vào prompt, 87% câu có tài liệu đúng.

Lưu ý khi đọc Hit@10: sau khử trùng nội dung và giới hạn 2 chunk mỗi nguồn, mỗi lượt chỉ còn trung bình 9.5 tài liệu riêng biệt - Hit@10 vì thế gần như đã chạm trần cấu trúc của rổ ứng viên, không phải trần chất lượng xếp hạng.
