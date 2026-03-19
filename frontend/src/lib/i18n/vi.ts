import type { TranslationKeys } from "./en";

const vi: Record<TranslationKeys, string> = {
  // Nav
  appName: "Insight",
  navDigest: "Bản tin",
  navSearch: "Tìm kiếm",
  navTimeline: "Dòng thời gian",

  // Common
  loading: "Đang tải...",
  errorBackend: "Không thể tải. Backend có đang chạy không?",

  // Digest
  digestNoDigest: "Không có bản tin cho ngày này.",
  digestErrorLoad: "Không thể tải bản tin. Backend có đang chạy không?",
  digestGoToday: "Về hôm nay",
  digestPrev: "trước",
  digestNext: "tiếp",
  digestItems: "mục",
  digestClusters: "cụm",
  digestMinRead: "phút đọc",
  digestConnections: "Kết nối",

  // Search
  searchPlaceholder: "Tìm kiếm kiến thức của bạn...",
  searching: "Đang tìm...",
  searchFailed: "Tìm kiếm thất bại. Backend có đang chạy không?",
  searchNoResults: "Không tìm thấy kết quả.",

  // Timeline
  timelineAll: "Tất cả",
  timelineBookmarks: "Dấu trang",
  timelineYouTube: "YouTube",
  timelineX: "X",
  timelineThreads: "Threads",
  timelineManual: "Thủ công",
  timelineLoadMore: "Tải thêm",
  timelineNoItems: "Chưa có mục nào.",
  timelineError: "Không thể tải mục. Backend có đang chạy không?",
};

export default vi;
