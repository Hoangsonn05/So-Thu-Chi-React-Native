/**
 * Gemini API Client
 * Tương đương với callGeminiApi() từ HamchinhActivity.java
 * 
 * Chứa logic HTTP request/response parsing từ original Android code
 */

const GEMINI_API_KEY = 'AIzaSyBk2tRqMVasNvZP13P9O5eymUiD-rSc31A';
const GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it:generateContent';

export interface GeminiAIResponse {
  so_tien: number;           // Amount
  ghi_chu: string;           // Note
  danh_muc: string;          // Category
  ngay: string;              // Date
  auto_submit: boolean;      // Auto-save transaction
  thong_bao: string;         // Notification message
  action_type: 'CHI' | 'THU'; // Expense or Income
}

export interface GeminiRequestPayload {
  contents: Array<{
    parts: Array<{
      text: string;
    }>;
  }>;
}

/**
 * Gọi Gemini API với prompt
 * @param prompt Prompt text
 * @returns Promise<GeminiAIResponse> Parsed AI response
 */
export async function callGeminiAPI(prompt: string): Promise<GeminiAIResponse> {
  const payload: GeminiRequestPayload = {
    contents: [
      {
        parts: [
          {
            text: prompt,
          },
        ],
      },
    ],
  };

  try {
    const response = await fetch(`${GEMINI_API_URL}?key=${GEMINI_API_KEY}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(
        `Gemini API Error: ${response.status} ${response.statusText}`
      );
    }

    const responseData = await response.json();

    // Extract AI text safely (tolerant to missing keys) - Tương tự Java code
    let aiAnswer: string | null = null;

    try {
      if (responseData.candidates && responseData.candidates[0]) {
        aiAnswer = responseData.candidates[0]?.content?.parts?.[0]?.text || null;
      }
    } catch (e) {
      console.error('Failed to extract text from candidates:', e);
    }

    if (!aiAnswer) {
      throw new Error('Empty response from Gemini API');
    }

    // Clean JSON markdown if present
    aiAnswer = aiAnswer.replace(/```json/g, '').replace(/```/g, '').trim();

    // Parse JSON response
    let resultData: GeminiAIResponse;
    try {
      resultData = JSON.parse(aiAnswer);
    } catch (ex) {
      // If aiAnswer is not a pure JSON object, try to locate a JSON substring
      const first = aiAnswer.indexOf('{');
      const last = aiAnswer.lastIndexOf('}');
      if (first >= 0 && last > first) {
        const sub = aiAnswer.substring(first, last + 1);
        resultData = JSON.parse(sub);
      } else {
        throw ex;
      }
    }

    // Validate and set defaults
    return {
      so_tien: resultData.so_tien || 0,
      ghi_chu: resultData.ghi_chu || '',
      danh_muc: resultData.danh_muc || '',
      ngay: resultData.ngay || '',
      auto_submit: resultData.auto_submit || false,
      thong_bao: resultData.thong_bao || '',
      action_type: resultData.action_type === 'THU' ? 'THU' : 'CHI',
    };
  } catch (error) {
    console.error('Gemini API call failed:', error);
    throw error;
  }
}
