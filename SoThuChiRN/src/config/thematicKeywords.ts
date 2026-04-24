/**
 * thematicKeywords.ts
 * Mapping of themes and categories to related keywords.
 * Used to expand search radius for thematic queries.
 */

export interface ThemeMapping {
  theme: string;
  keywords: string[];
}

export const THEMES: ThemeMapping[] = [
  {
    theme: 'Ăn uống',
    keywords: ['an', 'uong', 'com', 'pho', 'bun', 'mi', 'nuoc', 'thuc pham', 'food', 'drink', 'cafe', 'sua', 'tra', 'nha hang'],
  },
  {
    theme: 'Di chuyển',
    keywords: ['xe', 'xang', 'bus', 'grab', 'taxi', 'be', 'gojek', 'di lai', 'travel', 've may bay', 'tau hoa'],
  },
  {
    theme: 'Nhà cửa',
    keywords: ['dien', 'nuoc', 'rac', 'thue nha', 'internet', 'wifi', 'house', 'rent', 'sua chua', 'noi that'],
  },
  {
    theme: 'Sức khỏe',
    keywords: ['thuoc', 'benh', 'vien', 'kham', 'bac si', 'gym', 'yoga', 'health', 'fitness', 'spa'],
  },
  {
    theme: 'Giải trí',
    keywords: ['phim', 'nhac', 'game', 'dulich', 'choi', 'netflix', 'spotify', 'entertainment'],
  },
  {
    theme: 'Mua sắm',
    keywords: ['quan ao', 'giay', 'shopee', 'lazada', 'tiki', 'shopping', 'sieu thi', 'cho'],
  },
  {
    theme: 'Lương / Thu nhập',
    keywords: ['luong', 'thuong', 'bonus', 'salary', 'income', 'lai', 'tiet kiem'],
  },
];

/**
 * Checks if a query matches any thematic keywords and returns related category names.
 */
export const getRelatedCategories = (query: string): string[] => {
  const normalizedQuery = query.toLowerCase().trim();
  if (!normalizedQuery) return [];
  
  const queryWords = normalizedQuery.split(/\s+/);
  const matchedThemes: string[] = [];

  THEMES.forEach((t) => {
    // Stricter matching: 
    // 1. Check if any word in the query exactly matches a keyword
    // 2. OR check if any keyword is present in the query as a whole word (using regex)
    const hasMatch = t.keywords.some((kw) => {
      // Direct exact word match
      if (queryWords.includes(kw)) return true;
      
      // Handle multi-word keywords (e.g., 'thuc pham') using word boundary regex
      if (kw.includes(' ')) {
        const regex = new RegExp(`\\b${kw}\\b`, 'i');
        return regex.test(normalizedQuery);
      }
      
      return false;
    });

    if (hasMatch) {
      matchedThemes.push(t.theme);
    }
  });

  return matchedThemes;
};
