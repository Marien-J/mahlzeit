/** Matching text the way the server does: case, umlauts, accents and punctuation do not matter. */
export function normalize(text: string): string {
  return text
    .toLocaleLowerCase('de')
    .replace(/ß/g, 'ss')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}
