import { describe, expect, it } from 'vitest'
import de from './locales/de.json'
import en from './locales/en.json'
import nl from './locales/nl.json'

type Tree = { [key: string]: string | Tree }

function flatten(tree: Tree, prefix = ''): Record<string, string> {
  return Object.entries(tree).reduce<Record<string, string>>((out, [key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') out[path] = value
    else Object.assign(out, flatten(value, path))
    return out
  }, {})
}

const catalogues = { de: flatten(de), en: flatten(en), nl: flatten(nl) }
const variables = (text: string) => [...text.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort()

describe('translations', () => {
  it('have the same keys in German, English and Dutch', () => {
    const keys = Object.keys(catalogues.en).sort()
    expect(Object.keys(catalogues.de).sort()).toEqual(keys)
    expect(Object.keys(catalogues.nl).sort()).toEqual(keys)
  })

  it('use the same placeholders in every language', () => {
    for (const [key, text] of Object.entries(catalogues.en)) {
      expect(variables(catalogues.de[key] ?? ''), `de ${key}`).toEqual(variables(text))
      expect(variables(catalogues.nl[key] ?? ''), `nl ${key}`).toEqual(variables(text))
    }
  })

  it('have no empty strings', () => {
    for (const [lang, entries] of Object.entries(catalogues)) {
      for (const [key, text] of Object.entries(entries)) {
        expect(text.trim(), `${lang} ${key}`).not.toBe('')
      }
    }
  })
})
