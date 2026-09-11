module.exports = {
  content: ['./panel/templates/**/*.html', './panel/forms.py', './panel/templatetags/*.py', './panel/static/panel/*.js', './panel/views.py'],
  theme: {
    extend: {
      fontFamily: { sans: ['Vazirmatn', 'Tahoma', 'Arial', 'sans-serif'] },
      colors: { teal: { 50: '#edf5ef', 100: '#dbebe0', 200: '#b6d4bf', 600: '#477a62', 700: '#31634e', 800: '#254e3e', 900: '#203e35' } }
    }
  },
  plugins: []
};
