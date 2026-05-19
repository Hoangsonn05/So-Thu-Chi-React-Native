/**
 * Legacy AI client wrapper.
 *
 * Direct OpenRouter calls from Expo must not include server secrets. Keep this
 * module's public API stable so callers show their existing error state instead
 * of crashing, but require a backend proxy endpoint before AI can run here.
 */

export interface GeminiAIResponse {
  so_tien: number;
  ghi_chu: string;
  danh_muc: string;
  ngay: string;
  auto_submit: boolean;
  thong_bao: string;
  action_type: 'CHI' | 'THU' | 'CHAT';
  transaction_id?: string | null;
}

interface BackendAssistantResponse {
  success: boolean;
  message: string;
  intent: 'greeting' | 'transaction' | 'help' | 'unknown';
  transaction: {
    type?: number;
    amount?: number;
    category?: string;
    note?: string;
    date?: string;
  } | null;
  transaction_id: string | null;
}

export async function generateContent(
  prompt: string,
  options?: { firebaseUid?: string; mode?: 'auto' | 'transaction' | 'chat' }
): Promise<GeminiAIResponse> {
  const baseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    throw new Error('Chưa cấu hình EXPO_PUBLIC_API_BASE_URL.');
  }
  if (!options?.firebaseUid) {
    throw new Error('Bạn cần đăng nhập để dùng Trợ Lý AI.');
  }

  let payload: BackendAssistantResponse;
  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}/api/ai/assistant`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        firebase_uid: options.firebaseUid,
        message: prompt,
        mode: options.mode || 'auto',
      }),
    });

    if (!response.ok) {
      throw new Error(`backend_status_${response.status}`);
    }
    payload = await response.json();
  } catch (_error) {
    throw new Error('Không kết nối được backend AI. Vui lòng kiểm tra server.');
  }

  if (!payload.success) {
    throw new Error(payload.message || 'AI backend chưa sẵn sàng.');
  }

  if (!payload.transaction) {
    return {
      so_tien: 0,
      ghi_chu: payload.message,
      danh_muc: 'Trò chuyện',
      ngay: '',
      auto_submit: false,
      thong_bao: payload.message,
      action_type: 'CHAT',
      transaction_id: payload.transaction_id,
    };
  }

  return {
    so_tien: Number(payload.transaction.amount || 0),
    ghi_chu: payload.transaction.note || '',
    danh_muc: payload.transaction.category || '',
    ngay: payload.transaction.date || '',
    auto_submit: Boolean(payload.transaction.amount),
    thong_bao: payload.message,
    action_type: payload.transaction.type === 1 ? 'THU' : 'CHI',
    transaction_id: payload.transaction_id,
  };
}

export async function callGeminiAPI(
  prompt: string,
  options?: { firebaseUid?: string; mode?: 'auto' | 'transaction' | 'chat' }
): Promise<GeminiAIResponse> {
  return generateContent(prompt, options);
}
