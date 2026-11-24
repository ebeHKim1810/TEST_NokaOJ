/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        surface: {
          light: '#FFFFFF',
          subtle: '#F8F9FB',
          dark: '#0E1013',
          darkSubtle: '#15181E',
        },
        pastel: {
          blue: '#89B4E8',
          blueSoft: '#EBF3FC',
          blueText: '#2A5C99',
          green: '#84CBA3',
          greenSoft: '#EBF7F0',
          greenText: '#1F6F45',
          pink: '#E59CB4',
          pinkSoft: '#FDF0F4',
          pinkText: '#9B3558',
          orange: '#EDB57E',
          orangeSoft: '#FEF4EA',
          orangeText: '#945214',
        },
      },
    },
  },
  plugins: [],
};
