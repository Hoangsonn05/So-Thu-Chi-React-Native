type Listener = () => void;

class TransactionEvents {
  private listeners = new Set<Listener>();

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  emitChanged(): void {
    this.listeners.forEach((listener) => {
      try {
        listener();
      } catch (error) {
        console.error('TransactionEvents listener error:', error);
      }
    });
  }
}

export const transactionEvents = new TransactionEvents();
