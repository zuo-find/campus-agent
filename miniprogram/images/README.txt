小程序码 / 图片存放目录

用法：把小程序码图片放进本目录，然后在 life.js 顶部的 JUMP 配置里加一条
mode 为 'qrcode' 的条目，qr 指向本目录，例如：

  express_take: { mode: 'qrcode', qr: '/images/你的图片.png', name: '快递代取' }

页面会自动为这条生成一个入口卡片，用户点击后弹出小程序码、长按识别进入。
（若对方小程序有 AppID，更推荐用 mode:'appid' 一键跳转。）
