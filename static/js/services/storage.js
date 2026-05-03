

/**
 * storage.js — LocalStorage wrapper
 */

export const storage = {
    get(key, defaultValue = null) {
        try {
            const v = localStorage.getItem(key);
            return v !== null ? JSON.parse(v) : defaultValue;
        } catch {
            return defaultValue;
        }
    },

    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch { /* quota exceeded — ignore */ }
    },

    remove(key) {
        try {
            localStorage.removeItem(key);
        } catch { /* ignore */ }
    },
};


