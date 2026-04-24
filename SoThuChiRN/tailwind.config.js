/** @type {import('tailwindcss').Config} */
module.exports = {
  // NOTE: Update this to include the paths to all of your component files.
  content: ["./App.{js,jsx,ts,tsx}", "./src/**/*.{js,jsx,ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        background: "#0A0E17", // Dark Navy
        income: "#00E676",     // Mint Green
        expense: "#FF5252",    // Coral Red
        accent: "#00B0FF",     // Spatial Blue
        glass: {
          light: "rgba(255, 255, 255, 0.1)",
          dark: "rgba(0, 0, 0, 0.2)",
        }
      },
      borderRadius: {
        'bento': '24px',
      }
    },
  },
  plugins: [],
}
