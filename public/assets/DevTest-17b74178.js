import { n, F as o } from "./index-1f029c71.js";
const a = {
  name: "DevTest",
  components: { Form: o },
  data() {
    return { model: {} };
  },
  computed: {
    schema() {
      return {
        type: "object",
        properties: {
          sendGetSongCrawler: {
            type: "object",
            label: "Send",
            title: "Send get song crawler",
            objType: "button",
            onClick: () => {},
          },
          sendPressureTest: {
            type: "object",
            label: "Send",
            title: "Send get song pressure test",
            objType: "button",
            onClick: () => {},
          },
        },
      };
    },
  },
  watch: {},
  mounted() {},
  methods: {},
};
var r = function () {
    var t = this,
      e = t._self._c;
    return e("div", [
      e("div", { staticClass: "center_container" }, [
        e("div", { staticClass: "text-2xl text-left mb-10" }, [
          t._v("Development Tools"),
        ]),
        e(
          "div",
          { staticClass: "max-w-3xl w-[390px] text-left" },
          [e("Form", { attrs: { value: t.model, schema: t.schema } })],
          1,
        ),
      ]),
    ]);
  },
  c = [],
  l = n(a, r, c, !1, null, "d8c09d1d", null, null);
const _ = l.exports;
export { _ as default };
