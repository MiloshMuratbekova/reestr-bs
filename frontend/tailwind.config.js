/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        afm: {
          50: '#eef4fb',
          100: '#d7e5f5',
          200: '#b0cbe9',
          300: '#7fa9d8',
          400: '#4d84c4',
          500: '#2b64a8',
          600: '#1f4d87',
          700: '#1a3d6b',
          800: '#173154',
          900: '#122641',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'Roboto', 'Arial', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 3px rgba(18, 38, 65, 0.08), 0 1px 2px rgba(18, 38, 65, 0.06)',
      },
    },
  },
  plugins: [],
}
