const path = require("path");
const HtmlWebpackPlugin = require("html-webpack-plugin");

module.exports = {
  entry: path.resolve(__dirname, "src/index.jsx"),
  output: { path: path.resolve(__dirname, "dist"), filename: "assets/[name].[contenthash].js", clean: true, publicPath: "/" },
  module: { rules: [
    { test: /\.jsx?$/, exclude: /node_modules/, use: "babel-loader" },
    { test: /\.css$/, use: ["style-loader", "css-loader"] }
  ]},
  resolve: { extensions: [".js", ".jsx"] },
  plugins: [new HtmlWebpackPlugin({ template: path.resolve(__dirname, "public/index.html") })],
  devServer: {
    historyApiFallback: { disableDotRule: true, rewrites: [{ from: /./, to: "/index.html" }] },
    hot: true,
    proxy: [{ context: ["/api"], target: "http://127.0.0.1:8000" }]
  },
  optimization: { splitChunks: { chunks: "all", maxSize: 240000 } },
  performance: { maxAssetSize: 300000, maxEntrypointSize: 300000 }
};
