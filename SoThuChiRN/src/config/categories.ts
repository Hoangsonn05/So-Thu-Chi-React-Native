/**
 * categories.ts
 * Centralized categories for the application.
 */

export interface CategoryItem {
  name: string;
  emoji: string;
}

export const EXPENSE_CATEGORIES: CategoryItem[] = [
  { name: 'Ăn uống', emoji: '🍜' },
  { name: 'Chi tiêu', emoji: '🛒' },
  { name: 'Quần áo', emoji: '👕' },
  { name: 'Mỹ phẩm', emoji: '💄' },
  { name: 'Giao lưu', emoji: '🍻' },
  { name: 'Y tế', emoji: '🏥' },
  { name: 'Giáo dục', emoji: '📚' },
  { name: 'Tiền điện', emoji: '⚡' },
  { name: 'Du lịch', emoji: '✈️' },
  { name: 'Liên lạc', emoji: '📱' },
  { name: 'Tiền nhà', emoji: '🏠' },
  { name: 'Khác', emoji: '📦' },
];

export const INCOME_CATEGORIES: CategoryItem[] = [
  { name: 'Tiền lương', emoji: '💵' },
  { name: 'Tiền phụ cấp', emoji: '💰' },
  { name: 'Tiền thưởng', emoji: '🎁' },
  { name: 'Thu nhập phụ', emoji: '➕' },
  { name: 'Đầu tư', emoji: '📈' },
  { name: 'Thu nhập tạm', emoji: '🔄' },
  { name: 'Khác', emoji: '✏️' },
];

/**
 * Returns the emoji for a given category name.
 */
export const getCategoryEmoji = (name: string): string => {
  const all = [...EXPENSE_CATEGORIES, ...INCOME_CATEGORIES];
  const found = all.find(c => c.name === name);
  return found ? found.emoji : '📝'; // Default emoji if not found
};
