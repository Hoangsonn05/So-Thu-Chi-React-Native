/**
 * Gemini API Client
 * Tương đương với callGeminiApi() từ HamchinhActivity.java
 * 
 * Chứa logic HTTP request/response parsing từ original Android code
 */

const OPENROUTER_API_KEY = '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';
const OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions';
const MODEL_NAME = 'nvidia/nemotron-3-super-120b-a12b:free';

export interface GeminiAIResponse {
  so_tien: number;           // Amount
  ghi_chu: string;           // Note
  danh_muc: string;          // Category
  ngay: string;              // Date
  auto_submit: boolean;      // Auto-save transaction
  thong_bao: string;         // Notification message
  action_type: 'CHI' | 'THU'; // Expense or Income
}

/**
 * Gọi OpenRouter API với prompt (Thay thế Gemini)
 * @param prompt Prompt text
 * @returns Promise<GeminiAIResponse> Parsed AI response
 */
export async function callGeminiAPI(prompt: string): Promise<GeminiAIResponse> {
  const payload = {
    model: MODEL_NAME,
    messages: [
      {
        role: 'user',
        content: prompt,
      },
    ],
  };

  try {
    const response = await fetch(OPENROUTER_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${OPENROUTER_API_KEY}`,
        'HTTP-Referer': 'https://github.com/Hoangsonn05/So-Thu-Chi-React-Native', // Optional for OpenRouter
        'X-Title': 'So Thu Chi App', // Optional for OpenRouter
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorData = await response.text();
      throw new Error(
        `OpenRouter API Error: ${response.status} ${response.statusText} - ${errorData}`
      );
    }

    const responseData = await response.json();

    // Extract AI text từ OpenAI structure (choices[0].message.content)
    let aiAnswer: string | null = null;

    try {
      if (responseData.choices && responseData.choices[0]) {
        aiAnswer = responseData.choices[0]?.message?.content || null;
      }
    } catch (e) {
      console.error('Failed to extract text from choices:', e);
    }

    if (!aiAnswer) {
      throw new Error('Empty response from OpenRouter API');
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
    console.error('OpenRouter API call failed:', error);
    throw error;
  }
}
