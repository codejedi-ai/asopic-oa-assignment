/// <reference types="@ice/app/types" />

declare module '*.png' {
  const value: string;
  export default value;
}

declare global {
  interface Window {
    VANTA: {
      TOPOLOGY: (options: any) => any;
    };
  }
}
