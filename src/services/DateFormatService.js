import { useUserPreferencesStore } from '@/stores/userPreferences'

export class DateFormatService {
  static _instance = null

  static getInstance() {
    if (!this._instance) {
      this._instance = new DateFormatService()
    }
    return this._instance
  }

  _parseDate(value) {
    if (!value) return null
    if (value instanceof Date) return isNaN(value.getTime()) ? null : value
    if (typeof value !== 'string' && typeof value !== 'number') return null

    const s = String(value).trim()
    if (!s) return null

    // Unified pattern: 2026-04-19 20:54:44 or 2026-05-24T14:57:51.019848 or 2026-05-24
    const match = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?$/) ||
                  s.match(/^(\d{4})-(\d{2})-(\d{2})$/)
    if (match) {
      const [, year, month, day, hour = '0', minute = '0', second = '0'] = match
      const d = new Date(
        parseInt(year, 10),
        parseInt(month, 10) - 1,
        parseInt(day, 10),
        parseInt(hour, 10),
        parseInt(minute, 10),
        parseInt(second, 10)
      )
      return isNaN(d.getTime()) ? null : d
    }

    const d = new Date(s)
    return isNaN(d.getTime()) ? null : d
  }

  format(date, options = {}) {
    const pref = useUserPreferencesStore()
    const locale = options.locale || pref.locale || 'zh-CN'
    const dateStyle = options.dateStyle || pref.dateStyle || 'medium'
    const timeStyle = options.timeStyle || pref.timeStyle || 'short'
    const timeZone = options.timeZone || pref.timezone || this.detectTimezone()
    const hourCycle = options.hourCycle || pref.hourCycle || 24

    const parsed = this._parseDate(date)
    if (!parsed) return '-'

    try {
      const formatter = new Intl.DateTimeFormat(locale, {
        dateStyle,
        timeStyle,
        timeZone,
        hourCycle: hourCycle === 24 ? 'h23' : 'h12',
      })
      return formatter.format(parsed)
    } catch (e) {
      console.warn('[DateFormatService] Format error:', e)
      return '-'
    }
  }

  formatDate(date, options = {}) {
    return this.format(date, { ...options, timeStyle: undefined })
  }

  formatTime(date, options = {}) {
    return this.format(date, { ...options, dateStyle: undefined })
  }

  detectTimezone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone
    } catch {
      return 'UTC'
    }
  }
}

export const dateFormatService = DateFormatService.getInstance()
