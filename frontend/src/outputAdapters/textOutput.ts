export interface OutputAdapter {
  render(message: string): Promise<string>;
  isAvailable(): boolean;
}


export class TextOutputAdapter implements OutputAdapter {
  async render(message: string): Promise<string> {
    return message;
  }

  isAvailable(): boolean {
    return true;
  }
}


export const defaultOutputAdapter = new TextOutputAdapter();
