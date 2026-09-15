# 2.2. Các nền tảng và mô hình sử dụng

Hệ thống được xây dựng theo hướng chạy hoàn toàn cục bộ trên máy tính cá nhân, không phụ thuộc dịch vụ trả phí hay kết nối Internet trong quá trình hỏi – đáp. Định hướng đó chi phối toàn bộ việc lựa chọn nền tảng: mọi thành phần được trình bày dưới đây đều là phần mềm nguồn mở, có thể cài đặt và vận hành trên một máy cấu hình phổ thông, chỉ dùng CPU. Chín công cụ và mô hình chính hợp thành bốn lớp chức năng của hệ thống: lớp suy luận ngôn ngữ (Ollama, bge-m3, qwen3.5:4b), lớp truy hồi thông tin (FAISS, BM25), lớp điều phối và phục vụ (LangChain, FastAPI + Uvicorn) và lớp tiền xử lý dữ liệu đa phương thức (Tesseract OCR, faster-whisper).

## 2.2.1. Ollama

Ollama là nền tảng cho phép tải về, quản lý và thực thi các mô hình ngôn ngữ lớn ngay trên máy cục bộ. Công cụ này đóng gói trọng số mô hình cùng tham số cấu hình thành một đơn vị duy nhất và cung cấp một máy chủ HTTP cục bộ, mặc định lắng nghe tại địa chỉ `http://localhost:11434`. Nhờ đó, mọi thành phần khác của hệ thống chỉ cần gọi tới một điểm truy cập thống nhất, thay vì phải tự nạp trọng số và quản lý bộ nhớ cho từng mô hình.

Trong đồ án, Ollama phiên bản 0.34.0 giữ vai trò tầng thực thi cho cả hai loại mô hình: mô hình nhúng văn bản và mô hình sinh câu trả lời. Hệ thống giao tiếp với Ollama theo hai đường: thông qua các lớp bao `ChatOllama` và `OllamaEmbeddings` của LangChain cho luồng hỏi – đáp chính, và thông qua lời gọi HTTP trực tiếp tới các đầu cuối `/api/chat`, `/api/tags` cho những tác vụ phụ trợ như trích xuất siêu dữ liệu văn bản, liệt kê mô hình đang có và kiểm tra tình trạng kết nối. Địa chỉ máy chủ được đọc từ biến môi trường `OLLAMA_BASE_URL`, cho phép chuyển sang một máy chủ Ollama khác trong mạng nội bộ mà không phải sửa mã nguồn.

Việc lựa chọn Ollama xuất phát từ ba lý do. Thứ nhất, dữ liệu được xử lý là tài liệu nội bộ của đơn vị giáo dục, nên yêu cầu không gửi nội dung ra dịch vụ bên ngoài là yêu cầu bắt buộc. Thứ hai, nền tảng này hỗ trợ sẵn các mô hình đã lượng tử hóa, giúp mô hình vài tỉ tham số vẫn chạy được trong giới hạn bộ nhớ của máy tính cá nhân. Thứ ba, khả năng thay đổi mô hình chỉ bằng một tên gọi giúp hệ thống cho phép người dùng chuyển đổi giữa các mô hình trả lời ngay trên giao diện, phục vụ trực tiếp cho việc thử nghiệm và đánh giá ở chương sau.

## 2.2.2. Mô hình embedding bge-m3

bge-m3 là mô hình nhúng văn bản đa ngữ, có nhiệm vụ chuyển một đoạn văn bản thành một vector số thực biểu diễn ngữ nghĩa của đoạn văn đó. Hai đoạn văn có nội dung gần nhau sẽ cho hai vector gần nhau trong không gian vector, và đây chính là cơ sở để hệ thống tìm kiếm theo ngữ nghĩa thay vì tìm kiếm theo mặt chữ.

Trong hệ thống, bge-m3 được nạp qua Ollama với dung lượng khoảng 1,2 GB và sinh ra vector 1024 chiều. Mô hình này được dùng ở ba vị trí: mã hóa toàn bộ các đoạn tài liệu trong quá trình xây dựng kho tri thức, mã hóa câu hỏi của người dùng tại thời điểm truy vấn, và mã hóa câu hỏi phục vụ cơ chế bộ nhớ đệm ngữ nghĩa – nơi hai câu hỏi khác nhau về câu chữ nhưng cùng ý nghĩa sẽ dùng lại được câu trả lời đã sinh trước đó. Kho tri thức của đồ án tại thời điểm hoàn thiện chứa 25.761 vector, tương ứng với từng ấy đoạn văn bản được trích từ tập tài liệu giáo dục.

Lý do lựa chọn bge-m3 nằm ở đặc tính đa ngữ của mô hình. Tài liệu giáo dục tiếng Việt sử dụng dày đặc thuật ngữ hành chính và cấu trúc "Chương – Điều – Khoản", trong khi phần lớn mô hình nhúng phổ biến được huấn luyện chủ yếu trên tiếng Anh và cho chất lượng suy giảm rõ rệt khi gặp tiếng Việt có dấu. bge-m3 hỗ trợ tiếng Việt ngay trong tập huấn luyện gốc, đồng thời có kích thước đủ nhỏ để chạy trên CPU. Điểm hạn chế của mô hình – tốc độ mã hóa chậm khi chỉ có CPU – được hệ thống khắc phục bằng cách tách hẳn khâu xây dựng chỉ mục thành tiến trình chạy nền, và bằng việc lưu chỉ mục xuống đĩa để không phải mã hóa lại ở những lần khởi động sau.

## 2.2.3. Mô hình ngôn ngữ qwen3.5:4b

qwen3.5:4b là mô hình ngôn ngữ lớn quy mô khoảng bốn tỉ tham số, đã được lượng tử hóa xuống còn 3,4 GB, giữ vai trò sinh câu trả lời cuối cùng cho người dùng. Mô hình nhận đầu vào gồm câu hỏi và các đoạn tài liệu do khối truy hồi cung cấp, sau đó diễn đạt lại thành câu trả lời có dẫn nguồn.

Các tham số sinh văn bản được đặt theo hướng ưu tiên độ chính xác và thời gian phản hồi. Nhiệt độ (`temperature`) đặt ở mức 0,15 nhằm hạn chế tối đa hiện tượng mô hình tự bịa thông tin, vì với bài toán tra cứu văn bản quy phạm thì tính bám sát nguồn quan trọng hơn tính sáng tạo. Cửa sổ ngữ cảnh (`num_ctx`) đặt ở 4096 token và độ dài đầu ra tối đa (`num_predict`) đặt ở 420 token; hai giới hạn này xuất phát từ thực tế mỗi token đưa thêm vào ngữ cảnh đều phải trả giá bằng thời gian chờ khi suy luận trên CPU. Ngoài luồng trả lời chính, mô hình còn được dùng cho tác vụ trích xuất siêu dữ liệu của văn bản như số hiệu, ngày ban hành và cơ quan ban hành.

Hệ thống không ràng buộc cứng vào một mô hình duy nhất. Máy cài đặt còn có sẵn qwen3.5:9b, llama3.2:3b và qwen2.5:3b-instruct, và người dùng có thể đổi mô hình trả lời ngay trên giao diện. Việc chọn phiên bản bốn tỉ tham số làm mặc định là kết quả của sự đánh đổi: bản chín tỉ tham số cho câu trả lời mạch lạc hơn nhưng thời gian chờ tăng đáng kể trên máy chỉ có CPU, trong khi các mô hình ba tỉ tham số tuy nhanh hơn nhưng xử lý tiếng Việt hành chính kém ổn định hơn.

## 2.2.4. FAISS

FAISS (Facebook AI Similarity Search) là thư viện tìm kiếm tương đồng trên tập vector lớn. Thư viện này đảm nhận việc lưu trữ toàn bộ vector nhúng của kho tài liệu và trả về những vector gần nhất với vector câu hỏi trong thời gian chấp nhận được.

Đồ án sử dụng bản `faiss-cpu` phiên bản 1.15.0, truy cập gián tiếp qua lớp `FAISS` của LangChain. Chỉ mục được xây dựng theo kiểu `IndexFlatL2`, tức duyệt toàn bộ và đo khoảng cách Euclid, không dùng cấu trúc xấp xỉ. Lựa chọn này là có chủ đích: với quy mô khoảng hai mươi lăm nghìn vector, phép duyệt toàn bộ vẫn cho thời gian tìm kiếm dưới một giây, trong khi lại bảo đảm kết quả chính xác tuyệt đối thay vì gần đúng như các chỉ mục phân cụm hay đồ thị. Chỉ mục được lưu thành hai tệp trên đĩa – `index.faiss` chứa ma trận vector và `index.pkl` chứa nội dung cùng siêu dữ liệu của từng đoạn – nên chỉ cần xây dựng một lần và nạp lại tức thì ở các phiên làm việc sau. Hệ thống cũng hỗ trợ cập nhật chỉ mục theo lô khi có tài liệu mới, thay vì phải dựng lại toàn bộ kho.

## 2.2.5. BM25

BM25 là hàm xếp hạng cổ điển của ngành truy hồi thông tin, chấm điểm mức độ liên quan giữa truy vấn và tài liệu dựa trên tần suất xuất hiện của từ khóa, có hiệu chỉnh theo độ dài tài liệu và độ hiếm của từ. Khác với tìm kiếm theo vector, BM25 làm việc trực tiếp trên mặt chữ.

Trong đồ án, BM25 được sử dụng qua `BM25Retriever` của LangChain, bên dưới là thư viện `rank-bm25` phiên bản 0.2.2. Sự có mặt của thành phần này xuất phát từ một hạn chế quan sát được khi thử nghiệm: với những câu hỏi ngắn, mang tính định danh chính xác như "Điều 58 quy định gì?", mô hình nhúng ngữ nghĩa thường không xếp đúng đoạn văn cần tìm lên đầu, trong khi đây lại chính là điểm mạnh của tìm kiếm từ khóa. Để BM25 hoạt động tốt với tiếng Việt, hệ thống bổ sung một bước tách từ riêng có loại bỏ hư từ và mở rộng truy vấn hai chiều cho các từ viết tắt thông dụng trong ngành giáo dục, chẳng hạn ánh xạ giữa "TKB" và "thời khóa biểu", giữa "PPCT" và "phân phối chương trình".

Hai hướng tìm kiếm được hợp nhất bằng thuật toán Reciprocal Rank Fusion với hằng số k bằng 60. Cụ thể, mỗi bộ truy hồi trả về 15 ứng viên, điểm hợp nhất của một đoạn được tính theo nghịch đảo thứ hạng của nó trong từng danh sách, và bốn đoạn có điểm cao nhất được đưa vào ngữ cảnh của mô hình ngôn ngữ, với ràng buộc mỗi tài liệu nguồn đóng góp tối đa hai đoạn. Cách phối hợp này giúp hệ thống vừa giữ được khả năng hiểu ý của tìm kiếm ngữ nghĩa, vừa không bỏ sót những câu hỏi tra cứu chính xác theo số hiệu.

## 2.2.6. LangChain

LangChain là khung phần mềm chuyên dùng để xây dựng ứng dụng trên nền mô hình ngôn ngữ lớn. Vai trò của nó trong hệ thống là lớp điều phối: chuẩn hóa cách biểu diễn tài liệu, kết nối các thành phần rời rạc thành một chuỗi xử lý và che đi khác biệt giữa các nhà cung cấp mô hình.

Đồ án sử dụng LangChain theo kiến trúc phân rã thành nhiều gói: `langchain-core` (phiên bản 1.6.3) cung cấp kiểu dữ liệu `Document` dùng thống nhất trong toàn hệ thống cùng các lớp tạo khuôn nhắc và phân tích đầu ra; `langchain-ollama` cung cấp hai lớp kết nối tới máy chủ mô hình cục bộ; `langchain-community` cung cấp lớp bao cho FAISS, BM25 và các bộ nạp tài liệu theo định dạng; `langchain-text-splitters` cung cấp bộ tách văn bản đệ quy. Kích thước đoạn được đặt ở 1200 ký tự với phần chồng lấn 150 ký tự.

Điểm đáng lưu ý là hệ thống không dùng bộ tách văn bản mặc định một cách máy móc. Do đặc thù văn bản quy phạm trong lĩnh vực giáo dục, đồ án xây dựng thêm một lớp tách đoạn theo cấu trúc, ưu tiên giữ trọn vẹn một "Điều" cùng toàn bộ khoản và điểm bên trong nó thành một đoạn duy nhất; bộ tách đệ quy của LangChain chỉ được dùng làm phương án dự phòng khi tài liệu không có cấu trúc điều khoản hoặc khi một điều dài vượt quá ngưỡng 1200 ký tự. Đây là ví dụ cho thấy khung phần mềm được sử dụng như một tập công cụ nền, còn phần logic gắn với đặc thù dữ liệu vẫn do hệ thống tự đảm nhiệm.

## 2.2.7. FastAPI + Uvicorn

FastAPI là khung phát triển web bất đồng bộ cho Python, còn Uvicorn là máy chủ ASGI thực thi ứng dụng đó. Cặp công cụ này tạo nên tầng phục vụ của hệ thống: vừa cung cấp các đầu cuối API, vừa phục vụ trực tiếp các tệp tĩnh của giao diện người dùng.

Hệ thống hiện có khoảng hai mươi lăm đầu cuối, chia theo nhóm chức năng: hỏi – đáp, quản lý tài liệu và chỉ mục, quản lý mô hình, quản lý lịch sử hội thoại, quản lý tệp đính kèm và thống kê. Đầu cuối quan trọng nhất là `/api/chat/stream`, trả kết quả theo cơ chế truyền dòng để người dùng thấy câu trả lời hiện dần từng phần thay vì phải chờ toàn bộ quá trình suy luận kết thúc – một yêu cầu gần như bắt buộc khi mô hình chạy trên CPU và thời gian sinh một câu trả lời có thể lên tới hàng chục giây. FastAPI phiên bản 0.141.1 được chọn nhờ khả năng hỗ trợ sẵn kiểu trả về dạng dòng, tích hợp chặt với thư viện kiểm tra dữ liệu Pydantic và tự động sinh tài liệu API. Uvicorn phiên bản 0.52.4 đảm nhận việc chạy ứng dụng, trong đó những tác vụ đồng bộ nặng như truy hồi và suy luận được đẩy sang nhóm luồng riêng để không chặn vòng lặp sự kiện chính.

## 2.2.8. Tesseract OCR

Tesseract là công cụ nhận dạng ký tự quang học nguồn mở, dùng để rút văn bản từ ảnh. Trong hệ thống, thành phần này giải quyết một vấn đề rất thường gặp với kho tài liệu giáo dục: nhiều văn bản được lưu dưới dạng bản scan, tức tệp PDF chỉ chứa ảnh chụp trang giấy mà không có lớp văn bản nào để trích xuất.

Quy trình xử lý gồm ba bước. Trước hết, bộ nạp tài liệu kiểm tra xem tệp PDF có lớp văn bản hay không; nếu phát hiện trang trắng nội dung, hệ thống chuyển sang nhánh OCR. Tiếp theo, từng trang được kết xuất thành ảnh ở độ phân giải 300 DPI bằng thư viện `pypdfium2` – mức phân giải tiêu chuẩn cho văn bản in, vì thấp hơn thì dấu tiếng Việt rất dễ bị nhận sai. Cuối cùng, ảnh được đưa qua Tesseract phiên bản 5.4.0 với gói ngôn ngữ tiếng Việt `vie.traineddata` và chế độ phân tích bố cục trang tự động, phù hợp với dạng trình bày của văn bản hành chính.

Về mặt kỹ thuật tích hợp, hệ thống gọi Tesseract như một tiến trình dòng lệnh thông qua `subprocess` chứ không dùng thư viện bao `pytesseract`, nhằm kiểm soát trực tiếp tham số dòng lệnh và tránh thêm một lớp phụ thuộc. Do OCR là thao tác tốn thời gian, kết quả của mỗi tệp được lưu đệm theo mã băm nội dung, nhờ đó một tài liệu chỉ phải nhận dạng đúng một lần dù được nạp lại nhiều lần.

## 2.2.9. faster-whisper

faster-whisper là bản cài đặt lại mô hình nhận dạng tiếng nói Whisper trên nền thư viện suy luận CTranslate2, cho tốc độ cao hơn và tiêu tốn bộ nhớ ít hơn đáng kể so với bản gốc. Công cụ này mở rộng phạm vi dữ liệu đầu vào của hệ thống sang tệp âm thanh và video, chẳng hạn bản ghi tiết dạy hoặc video tập huấn chuyên môn.

Hệ thống dùng faster-whisper phiên bản 1.2.1 với mô hình kích thước `small`, chạy trên CPU ở chế độ lượng tử hóa số nguyên tám bit. Bộ lọc phát hiện tiếng nói được bật với ngưỡng khoảng lặng 500 mili-giây nhằm loại bỏ những đoạn im lặng – vốn là nguyên nhân khiến mô hình sinh ra văn bản không có thật. Kết quả phiên âm được lưu kèm dấu thời gian của từng đoạn, nhờ đó câu trả lời của hệ thống có thể trích dẫn chính xác tới phút thứ bao nhiêu trong video nguồn.

Một đặc điểm thiết kế cần nêu rõ: khâu phiên âm không nằm trong luồng hỏi – đáp trực tuyến. Người dùng chạy trước một kịch bản riêng để phiên âm toàn bộ tệp media thành văn bản lưu trên đĩa; đến khi nạp tài liệu, bộ nạp chỉ đọc lại bản phiên âm đã có sẵn. Cách tách rời này là cần thiết bởi phiên âm một video dài trên CPU có thể mất nhiều phút, hoàn toàn không phù hợp để thực hiện đồng thời với một phiên trò chuyện đang chờ phản hồi.

## 2.2.10. Các thư viện hỗ trợ khác

Bên cạnh chín thành phần cốt lõi nêu trên, hệ thống còn sử dụng một số thư viện đóng vai trò hỗ trợ. Tuy không quyết định kiến trúc, chúng là điều kiện để hệ thống làm việc được với dữ liệu thực tế vốn rất đa dạng về định dạng.

Nhóm thứ nhất phục vụ việc đọc tài liệu. Hệ thống hiện hỗ trợ hơn hai mươi phần mở rộng tệp, mỗi nhóm định dạng do một thư viện chuyên trách đảm nhiệm: `pypdf` đọc lớp văn bản của tệp PDF còn `pypdfium2` kết xuất trang PDF thành ảnh cho khâu OCR; `docx2txt` đọc tệp Word hiện hành, trong khi `pywin32` đọc tệp `.doc` đời cũ thông qua giao diện COM của Microsoft Word; `python-pptx` đọc bài trình chiếu; `pandas` cùng các thư viện nền `openpyxl` và `xlrd` đọc bảng tính và tệp phân tách bằng dấu. Riêng định dạng `.epub`, do bản chất là một gói nén chứa nhiều tệp XHTML, hệ thống tự cài đặt bộ đọc dựa trên `zipfile` và bộ phân tích XML của Python để duyệt đúng thứ tự các phần trong tệp mô tả nội dung.

Cần lưu ý rằng đồ án đã chủ động loại bỏ bộ nạp tài liệu vạn năng `UnstructuredFileLoader` vốn được nhiều tài liệu hướng dẫn khuyến nghị. Nguyên nhân là trong quá trình thử nghiệm, thư viện này treo hoặc gây lỗi bộ nhớ với toàn bộ tệp `.pptx` trong kho và với nhiều tệp `.docx`. Việc thay bằng các bộ đọc chuyên biệt cho từng định dạng tuy làm tăng khối lượng mã nguồn nhưng bảo đảm quá trình nạp dữ liệu chạy ổn định trên toàn bộ kho tài liệu.

Nhóm thứ hai phục vụ việc thu thập dữ liệu từ nguồn bên ngoài. Việc lấy tài liệu từ kho dùng chung được thực hiện qua Google Drive API phiên bản 3, gọi trực tiếp bằng thư viện `requests`; hệ thống lưu trạng thái đồng bộ nên những lần chạy sau chỉ tải về phần thay đổi thay vì tải lại toàn bộ. Bên cạnh đó, khi người dùng đưa một đường liên kết vào câu hỏi, hệ thống sẽ tự tải trang và dùng `trafilatura` bóc lấy nội dung chính, loại bỏ phần trình bày và quảng cáo. Thao tác tải trang này được kiểm soát an toàn: hệ thống từ chối những địa chỉ trỏ vào dải mạng nội bộ và kiểm tra lại từng bước chuyển hướng, nhằm ngăn nguy cơ bị lợi dụng để dò quét tài nguyên trong mạng của đơn vị.

Nhóm thứ ba phục vụ lưu trữ, bảo mật, giao diện và kiểm thử. Toàn bộ lịch sử hội thoại được lưu trong cơ sở dữ liệu `SQLite` – lựa chọn phù hợp với ứng dụng cục bộ vì không cần cài đặt máy chủ cơ sở dữ liệu riêng. Khi hệ thống được chạy ở chế độ công khai, một lớp trung gian xây trên `Starlette` sẽ yêu cầu xác thực tài khoản và mật khẩu, trong đó phép so sánh dùng hàm `hmac.compare_digest` để chống dạng tấn công suy đoán dựa trên thời gian phản hồi. Giao diện người dùng được viết bằng HTML, CSS và JavaScript thuần, không dùng khung phát triển giao diện nào, nhằm giữ cho việc triển khai đơn giản và không phát sinh bước biên dịch. Cuối cùng, chất lượng mã nguồn được bảo đảm bằng bộ kiểm thử tự động gồm mười sáu tệp chạy trên `pytest`, bao phủ các khối chức năng chính như truy hồi, phân loại tài liệu, lịch sử hội thoại, bộ nhớ đệm ngữ nghĩa và kiểm soát truy cập.

## Tổng hợp

Bảng dưới đây tóm tắt các thành phần đã trình bày cùng phiên bản và vai trò của từng thành phần trong hệ thống.

| Thành phần | Phiên bản | Vai trò trong hệ thống |
|---|---|---|
| Ollama | 0.34.0 | Máy chủ thực thi mô hình cục bộ tại cổng 11434 |
| bge-m3 | bản qua Ollama, 1024 chiều | Mã hóa ngữ nghĩa tài liệu và câu hỏi |
| qwen3.5:4b | 3,4 GB đã lượng tử hóa | Sinh câu trả lời, trích xuất siêu dữ liệu |
| FAISS | faiss-cpu 1.15.0 | Lưu trữ và tìm kiếm trên 25.761 vector |
| BM25 | rank-bm25 0.2.2 | Tìm kiếm theo từ khóa, bổ trợ cho tìm kiếm ngữ nghĩa |
| LangChain | core 1.6.3 và các gói đi kèm | Điều phối chuỗi xử lý, chuẩn hóa dữ liệu |
| FastAPI + Uvicorn | 0.141.1 và 0.52.4 | Tầng API và máy chủ phục vụ giao diện |
| Tesseract OCR | 5.4.0, gói ngôn ngữ vie | Rút văn bản từ tài liệu scan và ảnh |
| faster-whisper | 1.2.1 trên CTranslate2 4.8.2 | Phiên âm tệp âm thanh và video |
| Google Drive API v3 | gọi qua requests 2.34.2 | Đồng bộ tài liệu từ kho dùng chung |
| SQLite | bản đi kèm Python 3.12 | Lưu lịch sử hội thoại |
| Thư viện hỗ trợ | pypdf, pypdfium2, python-pptx, pandas, trafilatura, pytest… | Đọc đa định dạng, bóc nội dung web, kiểm thử |

Toàn bộ hệ thống được phát triển trên Python 3.12 và vận hành trong môi trường ảo độc lập. Điểm chung của các lựa chọn trên là đều hoạt động được không cần GPU và không cần kết nối tới dịch vụ bên ngoài, qua đó bảo đảm hai ràng buộc cốt lõi mà đồ án đặt ra ngay từ đầu: dữ liệu của đơn vị không rời khỏi máy cục bộ, và chi phí vận hành bằng không.
