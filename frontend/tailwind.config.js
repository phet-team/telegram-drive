/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        drive: {
          blue: '#1a73e8',
          hover: '#1765cc',
          bg: '#f8fafd',
          border: '#e0e3e7',
          sidebar: '#f0f4f9',
          selected: '#c2e7ff',
          selectedText: '#001d35'
        }
      }
    },
  },
  plugins: [],
}
