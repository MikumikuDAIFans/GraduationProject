export interface InputAdapter {
  parse(input: unknown): Promise<string>;
  isAvailable(): boolean;
}


export class TextInputAdapter implements InputAdapter {
  async parse(input: unknown): Promise<string> {
    if (typeof input === "string") return input;
    return String(input);
  }

  isAvailable(): boolean {
    return true;
  }
}


export const defaultInputAdapter = new TextInputAdapter();
