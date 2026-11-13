// Small observable state container; intentionally dependency-free.
export function createStore(initialState = {}) {
  let state = Object.freeze({ ...initialState });
  const listeners = new Set();
  return {
    getState: () => state,
    setState(update) {
      const patch = typeof update === "function" ? update(state) : update;
      if (!patch || typeof patch !== "object") return state;
      const next = Object.freeze({ ...state, ...patch });
      if (Object.keys(next).every(key => Object.is(next[key], state[key]))) return state;
      state = next;
      for (const listener of [...listeners]) listener(state);
      return state;
    },
    subscribe(listener) {
      if (typeof listener !== "function") throw new TypeError("listener must be a function");
      listeners.add(listener);
      return () => listeners.delete(listener);
    }
  };
}
