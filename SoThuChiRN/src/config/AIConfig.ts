/**
 * AI Assistant Configuration
 * 
 * Chứa prompts, categories, suggestions, và constant khác
 * cho AI feature
 */

export const AI_CONFIG = {
  // ============================================================================
  // SUGGESTION CHIPS
  // ============================================================================
  SUGGESTION_CHIPS: [
    '🍜 Phở sáng 45k',
    '☕ Cà phê 35k',
    '🚌 Đi buýt 7k',
    '💳 Thanh toán hóa đơn 2 triệu',
    '💼 Lương tháng 10 triệu',
    '🎓 Học phí 5 triệu',
  ],

  // ============================================================================
  // PROMPT TEMPLATES
  // ============================================================================
  SYSTEM_PROMPT: `Bạn là trợ lý AI thông minh, thân thiện.
  
Nhiệm vụ:
1. Phân loại rõ "Trò chuyện" và "Giao dịch".
2. Đối với Giao dịch: BẮT BUỘC dùng mẫu trả lời cũ: "✅ Đã ghi nhận [chi/thu] [số tiền] cho [hạng mục] vào lúc [giờ] ngày [ngày]".
3. Đối với Trò chuyện: Phản hồi linh hoạt, tự nhiên, KHÔNG ghi nhận bất kỳ khoản giao dịch nào (so_tien = 0, auto_submit = false).

Nguyên tắc trích xuất dữ liệu: 
- LUÔN trả về JSON object.
- Tuyệt đối giữ nguyên logic trích xuất dữ liệu kế thừa cho các trường số tiền, danh mục, hành động.`,

  EXPENSE_CATEGORIES: [
    'Ăn uống',
    'Chi tiêu hàng ngày',
    'Quần áo',
    'Mỹ phẩm',
    'Phí giao lưu',
    'Y tế',
    'Giáo dục',
    'Tiền điện',
    'Đi lại',
    'Phí liên lạc',
    'Tiền nhà',
    'Chỉnh sửa',
    'Giải trí',
    'Thể thao',
  ],

  INCOME_CATEGORIES: [
    'Tiền lương',
    'Tiền phụ cấp',
    'Tiền thưởng',
    'Thu nhập phụ',
    'Đầu tư',
    'Thu nhập tạm thời',
    'Chỉnh sửa',
  ],

  // ============================================================================
  // STATUS MESSAGES
  // ============================================================================
  MESSAGES: {
    LOADING: '✨ Chờ tớ chút nha ✨...',
    EMPTY_INPUT: 'Vui lòng nhập nội dung!',
    NETWORK_ERROR: '❌ Lỗi mạng: Không thể kết nối AI',
    EMPTY_RESPONSE: '❌ Lỗi: phản hồi rỗng từ AI',
    AUTO_SAVED: '✅ Đã lưu tự động',
    AUTO_SAVE_FAILED: '⚠️ Lỗi khi lưu - vui lòng thử lại',
    VOICE_NOT_SUPPORTED: '❌ Thiết bị không hỗ trộ nhập giọng nói',
    VOICE_PROMPT: 'Hãy nói nội dung giao dịch...',
  },

  // ============================================================================
  // UI TEXT
  // ============================================================================
  UI_TEXT: {
    HEADER_TITLE: 'Trợ Lý AI',
    HEADER_SUBTITLE: 'Tự động ghi chép chi tiêu của bạn',
    INPUT_PLACEHOLDER: 'Nói gì đi, tớ lắng nghe...',
    EMPTY_STATE_TEXT: 'Kể cho tôi về chi tiêu của bạn',
    EMPTY_STATE_SUBTEXT: 'Ví dụ: "Sáng nay ăn phở 45k" hoặc "Lương tháng 10 triệu"',
    CLOSE_BUTTON: 'Đóng',
    SEND_BUTTON: 'Gửi',
    VOICE_BUTTON: 'Giọng nói',
  },

  // ============================================================================
  // COLORS
  // ============================================================================
  COLORS: {
    PRIMARY: '#7C4DFF',
    SUCCESS: '#34C759',
    DANGER: '#FF3B30',
    WARNING: '#FF9500',
    BACKGROUND: '#F5F7FA',
    TEXT_PRIMARY: '#1D1D1F',
    TEXT_SECONDARY: '#86868B',
    BORDER: '#E8E8ED',
  },

  // ============================================================================
  // JSON RESPONSE SCHEMA
  // ============================================================================
  RESPONSE_SCHEMA: {
    so_tien: 'number - số tiền (VND)',
    ghi_chu: 'string - ghi chú giao dịch',
    danh_muc: 'string - danh mục chi tiêu',
    ngay: 'string - ngày (định dạng dd/MM/yyyy)',
    auto_submit: 'boolean - có tự động lưu hay không',
    thong_bao: 'string - thông báo cho người dùng',
    action_type: 'string - "CHI" hoặc "THU"',
  },
};

export const getAIConfig = () => AI_CONFIG;
