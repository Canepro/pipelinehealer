/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'azure': {
          50: '#f2f7fd',
          100: '#e2edf9',
          200: '#c2d9f2',
          300: '#96bee7',
          400: '#689fd8',
          500: '#4a86c7',
          600: '#356fae',
          700: '#2c5b8f',
          800: '#264d77',
          900: '#223f61',
        },
      },
    },
  },
  plugins: [],
}
