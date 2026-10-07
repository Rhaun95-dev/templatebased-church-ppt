const assert = require("node:assert");
const { parseHymnFilename } = require("../../static/js/hymn-library.js");

assert.deepStrictEqual(parseHymnFilename("001_만복의 근원 하나님.pptx"), { number: 1, title: "만복의 근원 하나님" });
assert.deepStrictEqual(parseHymnFilename("23 - 주님께 영광.PPTX"), { number: 23, title: "주님께 영광" });
assert.deepStrictEqual(parseHymnFilename("305.pptx"), { number: 305, title: "" });
assert.deepStrictEqual(parseHymnFilename("서문.pptx"), { number: null, title: "서문" });
assert.strictEqual(parseHymnFilename("~$001_x.pptx"), null);
assert.strictEqual(parseHymnFilename("001_x.ppt"), null);
assert.strictEqual(parseHymnFilename("notes.txt"), null);
console.log("hymn-library parse tests passed");
