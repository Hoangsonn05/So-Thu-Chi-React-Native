/**
 * textUtils.ts
 * Utilities for text normalization and diacritic removal.
 */

/**
 * Removes Vietnamese diacritics and converts to lowercase.
 * Example: "Ăn uống" -> "an uong"
 */
export const removeAccents = (str: string): string => {
  if (!str) return '';
  return str
    .normalize('NFD') // Separate base characters from their diacritics
    .replace(/[\u0300-\u036f]/g, '') // Remove diacritics
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'd') // Keep lowercase for consistency
    .toLowerCase()
    .trim();
};

/**
 * Normalizes a string for search comparisons.
 */
export const normalizeForSearch = (text: string): string => {
  return removeAccents(text);
};

/**
 * Prepares a search query by removing accents and splitting into words.
 */
export const prepareSearchQuery = (query: string): string => {
  const normalized = normalizeForSearch(query);
  // Replace multiple spaces with a single wildcard for SQL LIKE
  return `%${normalized.replace(/\s+/g, '%')}%`;
};
