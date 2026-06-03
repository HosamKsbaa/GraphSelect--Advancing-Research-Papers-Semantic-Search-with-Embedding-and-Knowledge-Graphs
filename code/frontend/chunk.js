import { injectQuery as __vite__injectQuery } from "/@vite/client";import { createHotContext as __vite__createHotContext } from "/@vite/client";import.meta.hot = __vite__createHotContext("/chunk-53A2BGWD.js");import {
  ApiService,
  api_service_exports
} from "/chunk-KEZQZXLR.js";
import {
  EmptyStateComponent
} from "/chunk-CAJNW4TV.js";
import "/chunk-EVSPGG2W.js";

// src/app/features/projects/project-list/project-list.page.ts
import { Component } from "/@fs/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/newcode/code/frontend/.angular/cache/21.2.13/alrs-frontend/vite/deps/@angular_core.js?v=7ea64484";
import { CommonModule } from "/@fs/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/newcode/code/frontend/.angular/cache/21.2.13/alrs-frontend/vite/deps/@angular_common.js?v=7ea64484";
import { RouterModule } from "/@fs/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/newcode/code/frontend/.angular/cache/21.2.13/alrs-frontend/vite/deps/@angular_router.js?v=7ea64484";
import { FormsModule } from "/@fs/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/newcode/code/frontend/.angular/cache/21.2.13/alrs-frontend/vite/deps/@angular_forms.js?v=7ea64484";

// src/app/shared/relative-time.pipe.ts
import { Pipe } from "/@fs/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/newcode/code/frontend/.angular/cache/21.2.13/alrs-frontend/vite/deps/@angular_core.js?v=7ea64484";
import * as i0 from "/@fs/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/newcode/code/frontend/.angular/cache/21.2.13/alrs-frontend/vite/deps/@angular_core.js?v=7ea64484";
var RelativeTimePipe = class _RelativeTimePipe {
  transform(value) {
    if (!value)
      return "";
    const date = new Date(value);
    if (isNaN(date.getTime()))
      return "";
    const now = /* @__PURE__ */ new Date();
    const diffMs = now.getTime() - date.getTime();
    if (diffMs < 0)
      return "in the future";
    const diffMins = Math.floor(diffMs / 6e4);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    if (diffMins < 1)
      return "now";
    if (diffMins < 60)
      return `${diffMins}m`;
    if (diffHours < 24)
      return `${diffHours}h`;
    return `${diffDays}d`;
  }
  static \u0275fac = function RelativeTimePipe_Factory(__ngFactoryType__) {
    return new (__ngFactoryType__ || _RelativeTimePipe)();
  };
  static \u0275pipe = /* @__PURE__ */ i0.\u0275\u0275definePipe({ name: "relativeTime", type: _RelativeTimePipe, pure: true });
};
(() => {
  (typeof ngDevMode === "undefined" || ngDevMode) && i0.\u0275setClassMetadata(RelativeTimePipe, [{
    type: Pipe,
    args: [{
      name: "relativeTime",
      standalone: true
    }]
  }], null, null);
})();

// src/app/features/projects/project-list/project-list.page.ts
import * as i02 from "/@fs/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/newcode/code/frontend/.angular/cache/21.2.13/alrs-frontend/vite/deps/@angular_core.js?v=7ea64484";
import * as i2 from "/@fs/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/newcode/code/frontend/.angular/cache/21.2.13/alrs-frontend/vite/deps/@angular_router.js?v=7ea64484";
import * as i3 from "/@fs/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/newcode/code/frontend/.angular/cache/21.2.13/alrs-frontend/vite/deps/@angular_common.js?v=7ea64484";
import * as i4 from "/@fs/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/newcode/code/frontend/.angular/cache/21.2.13/alrs-frontend/vite/deps/@angular_forms.js?v=7ea64484";
var _c0 = () => [1, 2, 3];
var _c1 = (a0) => ["/projects", a0];
var _forTrack0 = ($index, $item) => $item.id;
function ProjectListPage_Conditional_24_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275element(0, "app-empty-state", 20);
  }
  if (rf & 2) {
    const ctx_r0 = i02.\u0275\u0275nextContext();
    i02.\u0275\u0275property("ctaAction", ctx_r0.openCreateDialog.bind(ctx_r0));
  }
}
function ProjectListPage_Conditional_25_div_1_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275element(0, "div", 25);
  }
}
function ProjectListPage_Conditional_25_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "div", 21);
    i02.\u0275\u0275template(1, ProjectListPage_Conditional_25_div_1_Template, 1, 0, "div", 24);
    i02.\u0275\u0275elementEnd();
  }
  if (rf & 2) {
    i02.\u0275\u0275advance();
    i02.\u0275\u0275property("ngForOf", i02.\u0275\u0275pureFunction0(1, _c0));
  }
}
function ProjectListPage_Conditional_26_Conditional_1_For_7_Conditional_7_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "p", 36);
    i02.\u0275\u0275text(1);
    i02.\u0275\u0275elementEnd();
  }
  if (rf & 2) {
    const project_r2 = i02.\u0275\u0275nextContext().$implicit;
    i02.\u0275\u0275advance();
    i02.\u0275\u0275textInterpolate(project_r2.topic);
  }
}
function ProjectListPage_Conditional_26_Conditional_1_For_7_Conditional_8_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "p", 37);
    i02.\u0275\u0275text(1);
    i02.\u0275\u0275elementEnd();
  }
  if (rf & 2) {
    const project_r2 = i02.\u0275\u0275nextContext().$implicit;
    i02.\u0275\u0275advance();
    i02.\u0275\u0275textInterpolate(project_r2.description);
  }
}
function ProjectListPage_Conditional_26_Conditional_1_For_7_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "a", 32)(1, "div", 33)(2, "h3", 34);
    i02.\u0275\u0275text(3);
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(4, "span", 35);
    i02.\u0275\u0275text(5);
    i02.\u0275\u0275pipe(6, "relativeTime");
    i02.\u0275\u0275elementEnd()();
    i02.\u0275\u0275conditionalCreate(7, ProjectListPage_Conditional_26_Conditional_1_For_7_Conditional_7_Template, 2, 1, "p", 36);
    i02.\u0275\u0275conditionalCreate(8, ProjectListPage_Conditional_26_Conditional_1_For_7_Conditional_8_Template, 2, 1, "p", 37);
    i02.\u0275\u0275elementStart(9, "div", 38)(10, "span", 39);
    i02.\u0275\u0275text(11);
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(12, "span", 40);
    i02.\u0275\u0275text(13);
    i02.\u0275\u0275elementEnd()()();
  }
  if (rf & 2) {
    const project_r2 = ctx.$implicit;
    i02.\u0275\u0275property("routerLink", i02.\u0275\u0275pureFunction1(9, _c1, project_r2.id));
    i02.\u0275\u0275advance(3);
    i02.\u0275\u0275textInterpolate(project_r2.name);
    i02.\u0275\u0275advance(2);
    i02.\u0275\u0275textInterpolate(i02.\u0275\u0275pipeBind1(6, 7, project_r2.updated_at));
    i02.\u0275\u0275advance(2);
    i02.\u0275\u0275conditional(project_r2.topic ? 7 : -1);
    i02.\u0275\u0275advance();
    i02.\u0275\u0275conditional(project_r2.description ? 8 : -1);
    i02.\u0275\u0275advance(3);
    i02.\u0275\u0275textInterpolate1("", project_r2.paper_count, " Papers");
    i02.\u0275\u0275advance(2);
    i02.\u0275\u0275textInterpolate1("", project_r2.question_count, " Questions");
  }
}
function ProjectListPage_Conditional_26_Conditional_1_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "section", 26)(1, "h2", 29);
    i02.\u0275\u0275text(2, "Master Level ");
    i02.\u0275\u0275elementStart(3, "span", 30);
    i02.\u0275\u0275text(4);
    i02.\u0275\u0275elementEnd()();
    i02.\u0275\u0275elementStart(5, "div", 31);
    i02.\u0275\u0275repeaterCreate(6, ProjectListPage_Conditional_26_Conditional_1_For_7_Template, 14, 11, "a", 32, _forTrack0);
    i02.\u0275\u0275elementEnd()();
  }
  if (rf & 2) {
    const ctx_r0 = i02.\u0275\u0275nextContext(2);
    i02.\u0275\u0275advance(4);
    i02.\u0275\u0275textInterpolate(ctx_r0.masterProjects.length);
    i02.\u0275\u0275advance(2);
    i02.\u0275\u0275repeater(ctx_r0.masterProjects);
  }
}
function ProjectListPage_Conditional_26_Conditional_2_For_7_Conditional_7_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "p", 36);
    i02.\u0275\u0275text(1);
    i02.\u0275\u0275elementEnd();
  }
  if (rf & 2) {
    const project_r3 = i02.\u0275\u0275nextContext().$implicit;
    i02.\u0275\u0275advance();
    i02.\u0275\u0275textInterpolate(project_r3.topic);
  }
}
function ProjectListPage_Conditional_26_Conditional_2_For_7_Conditional_8_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "p", 37);
    i02.\u0275\u0275text(1);
    i02.\u0275\u0275elementEnd();
  }
  if (rf & 2) {
    const project_r3 = i02.\u0275\u0275nextContext().$implicit;
    i02.\u0275\u0275advance();
    i02.\u0275\u0275textInterpolate(project_r3.description);
  }
}
function ProjectListPage_Conditional_26_Conditional_2_For_7_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "a", 32)(1, "div", 33)(2, "h3", 34);
    i02.\u0275\u0275text(3);
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(4, "span", 35);
    i02.\u0275\u0275text(5);
    i02.\u0275\u0275pipe(6, "relativeTime");
    i02.\u0275\u0275elementEnd()();
    i02.\u0275\u0275conditionalCreate(7, ProjectListPage_Conditional_26_Conditional_2_For_7_Conditional_7_Template, 2, 1, "p", 36);
    i02.\u0275\u0275conditionalCreate(8, ProjectListPage_Conditional_26_Conditional_2_For_7_Conditional_8_Template, 2, 1, "p", 37);
    i02.\u0275\u0275elementStart(9, "div", 38)(10, "span", 39);
    i02.\u0275\u0275text(11);
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(12, "span", 40);
    i02.\u0275\u0275text(13);
    i02.\u0275\u0275elementEnd()()();
  }
  if (rf & 2) {
    const project_r3 = ctx.$implicit;
    i02.\u0275\u0275property("routerLink", i02.\u0275\u0275pureFunction1(9, _c1, project_r3.id));
    i02.\u0275\u0275advance(3);
    i02.\u0275\u0275textInterpolate(project_r3.name);
    i02.\u0275\u0275advance(2);
    i02.\u0275\u0275textInterpolate(i02.\u0275\u0275pipeBind1(6, 7, project_r3.updated_at));
    i02.\u0275\u0275advance(2);
    i02.\u0275\u0275conditional(project_r3.topic ? 7 : -1);
    i02.\u0275\u0275advance();
    i02.\u0275\u0275conditional(project_r3.description ? 8 : -1);
    i02.\u0275\u0275advance(3);
    i02.\u0275\u0275textInterpolate1("", project_r3.paper_count, " Papers");
    i02.\u0275\u0275advance(2);
    i02.\u0275\u0275textInterpolate1("", project_r3.question_count, " Questions");
  }
}
function ProjectListPage_Conditional_26_Conditional_2_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "section", 26)(1, "h2", 29);
    i02.\u0275\u0275text(2, "PhD Level ");
    i02.\u0275\u0275elementStart(3, "span", 30);
    i02.\u0275\u0275text(4);
    i02.\u0275\u0275elementEnd()();
    i02.\u0275\u0275elementStart(5, "div", 31);
    i02.\u0275\u0275repeaterCreate(6, ProjectListPage_Conditional_26_Conditional_2_For_7_Template, 14, 11, "a", 32, _forTrack0);
    i02.\u0275\u0275elementEnd()();
  }
  if (rf & 2) {
    const ctx_r0 = i02.\u0275\u0275nextContext(2);
    i02.\u0275\u0275advance(4);
    i02.\u0275\u0275textInterpolate(ctx_r0.phdProjects.length);
    i02.\u0275\u0275advance(2);
    i02.\u0275\u0275repeater(ctx_r0.phdProjects);
  }
}
function ProjectListPage_Conditional_26_Conditional_3_For_7_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "a", 42)(1, "div", 33)(2, "h3", 43);
    i02.\u0275\u0275text(3);
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(4, "span", 35);
    i02.\u0275\u0275text(5);
    i02.\u0275\u0275pipe(6, "relativeTime");
    i02.\u0275\u0275elementEnd()();
    i02.\u0275\u0275elementStart(7, "div", 44)(8, "span", 41);
    i02.\u0275\u0275text(9, "Archived");
    i02.\u0275\u0275elementEnd()()();
  }
  if (rf & 2) {
    const project_r4 = ctx.$implicit;
    i02.\u0275\u0275property("routerLink", i02.\u0275\u0275pureFunction1(5, _c1, project_r4.id));
    i02.\u0275\u0275advance(3);
    i02.\u0275\u0275textInterpolate(project_r4.name);
    i02.\u0275\u0275advance(2);
    i02.\u0275\u0275textInterpolate(i02.\u0275\u0275pipeBind1(6, 3, project_r4.updated_at));
  }
}
function ProjectListPage_Conditional_26_Conditional_3_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "section", 27)(1, "h2", 29);
    i02.\u0275\u0275text(2, "Archived ");
    i02.\u0275\u0275elementStart(3, "span", 41);
    i02.\u0275\u0275text(4);
    i02.\u0275\u0275elementEnd()();
    i02.\u0275\u0275elementStart(5, "div", 31);
    i02.\u0275\u0275repeaterCreate(6, ProjectListPage_Conditional_26_Conditional_3_For_7_Template, 10, 7, "a", 42, _forTrack0);
    i02.\u0275\u0275elementEnd()();
  }
  if (rf & 2) {
    const ctx_r0 = i02.\u0275\u0275nextContext(2);
    i02.\u0275\u0275advance(4);
    i02.\u0275\u0275textInterpolate(ctx_r0.archivedProjects.length);
    i02.\u0275\u0275advance(2);
    i02.\u0275\u0275repeater(ctx_r0.archivedProjects);
  }
}
function ProjectListPage_Conditional_26_Conditional_4_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "div", 28);
    i02.\u0275\u0275text(1);
    i02.\u0275\u0275elementEnd();
  }
  if (rf & 2) {
    const ctx_r0 = i02.\u0275\u0275nextContext(2);
    i02.\u0275\u0275advance();
    i02.\u0275\u0275textInterpolate1(' No projects matching "', ctx_r0.searchQuery, '" ');
  }
}
function ProjectListPage_Conditional_26_Template(rf, ctx) {
  if (rf & 1) {
    i02.\u0275\u0275elementStart(0, "div", 22);
    i02.\u0275\u0275conditionalCreate(1, ProjectListPage_Conditional_26_Conditional_1_Template, 8, 1, "section", 26);
    i02.\u0275\u0275conditionalCreate(2, ProjectListPage_Conditional_26_Conditional_2_Template, 8, 1, "section", 26);
    i02.\u0275\u0275conditionalCreate(3, ProjectListPage_Conditional_26_Conditional_3_Template, 8, 1, "section", 27);
    i02.\u0275\u0275conditionalCreate(4, ProjectListPage_Conditional_26_Conditional_4_Template, 2, 1, "div", 28);
    i02.\u0275\u0275elementEnd();
  }
  if (rf & 2) {
    const ctx_r0 = i02.\u0275\u0275nextContext();
    i02.\u0275\u0275advance();
    i02.\u0275\u0275conditional(ctx_r0.masterProjects.length > 0 ? 1 : -1);
    i02.\u0275\u0275advance();
    i02.\u0275\u0275conditional(ctx_r0.phdProjects.length > 0 ? 2 : -1);
    i02.\u0275\u0275advance();
    i02.\u0275\u0275conditional(ctx_r0.archivedProjects.length > 0 ? 3 : -1);
    i02.\u0275\u0275advance();
    i02.\u0275\u0275conditional(ctx_r0.projects.length > 0 && ctx_r0.masterProjects.length === 0 && ctx_r0.phdProjects.length === 0 && ctx_r0.archivedProjects.length === 0 ? 4 : -1);
  }
}
function ProjectListPage_Conditional_27_Template(rf, ctx) {
  if (rf & 1) {
    const _r5 = i02.\u0275\u0275getCurrentView();
    i02.\u0275\u0275elementStart(0, "div", 23)(1, "div", 45)(2, "div", 46)(3, "h2", 47);
    i02.\u0275\u0275text(4, "New Project");
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(5, "button", 48);
    i02.\u0275\u0275listener("click", function ProjectListPage_Conditional_27_Template_button_click_5_listener() {
      i02.\u0275\u0275restoreView(_r5);
      const ctx_r0 = i02.\u0275\u0275nextContext();
      return i02.\u0275\u0275resetView(ctx_r0.closeCreateDialog());
    });
    i02.\u0275\u0275namespaceSVG();
    i02.\u0275\u0275elementStart(6, "svg", 49);
    i02.\u0275\u0275element(7, "line", 50)(8, "line", 51);
    i02.\u0275\u0275elementEnd()()();
    i02.\u0275\u0275namespaceHTML();
    i02.\u0275\u0275elementStart(9, "form", 52);
    i02.\u0275\u0275listener("ngSubmit", function ProjectListPage_Conditional_27_Template_form_ngSubmit_9_listener() {
      i02.\u0275\u0275restoreView(_r5);
      const ctx_r0 = i02.\u0275\u0275nextContext();
      return i02.\u0275\u0275resetView(ctx_r0.createProject());
    });
    i02.\u0275\u0275elementStart(10, "div", 53)(11, "label", 54);
    i02.\u0275\u0275text(12, "Project Name ");
    i02.\u0275\u0275elementStart(13, "span", 55);
    i02.\u0275\u0275text(14, "*");
    i02.\u0275\u0275elementEnd()();
    i02.\u0275\u0275elementStart(15, "input", 56);
    i02.\u0275\u0275twoWayListener("ngModelChange", function ProjectListPage_Conditional_27_Template_input_ngModelChange_15_listener($event) {
      i02.\u0275\u0275restoreView(_r5);
      const ctx_r0 = i02.\u0275\u0275nextContext();
      i02.\u0275\u0275twoWayBindingSet(ctx_r0.newProject.name, $event) || (ctx_r0.newProject.name = $event);
      return i02.\u0275\u0275resetView($event);
    });
    i02.\u0275\u0275elementEnd()();
    i02.\u0275\u0275elementStart(16, "div", 53)(17, "label", 57);
    i02.\u0275\u0275text(18, "Topic");
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(19, "input", 58);
    i02.\u0275\u0275twoWayListener("ngModelChange", function ProjectListPage_Conditional_27_Template_input_ngModelChange_19_listener($event) {
      i02.\u0275\u0275restoreView(_r5);
      const ctx_r0 = i02.\u0275\u0275nextContext();
      i02.\u0275\u0275twoWayBindingSet(ctx_r0.newProject.topic, $event) || (ctx_r0.newProject.topic = $event);
      return i02.\u0275\u0275resetView($event);
    });
    i02.\u0275\u0275elementEnd()();
    i02.\u0275\u0275elementStart(20, "div", 53)(21, "label", 59);
    i02.\u0275\u0275text(22, "Target Level");
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(23, "select", 60);
    i02.\u0275\u0275twoWayListener("ngModelChange", function ProjectListPage_Conditional_27_Template_select_ngModelChange_23_listener($event) {
      i02.\u0275\u0275restoreView(_r5);
      const ctx_r0 = i02.\u0275\u0275nextContext();
      i02.\u0275\u0275twoWayBindingSet(ctx_r0.newProject.target_level, $event) || (ctx_r0.newProject.target_level = $event);
      return i02.\u0275\u0275resetView($event);
    });
    i02.\u0275\u0275elementStart(24, "option", 61);
    i02.\u0275\u0275text(25, "Master Level");
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(26, "option", 62);
    i02.\u0275\u0275text(27, "PhD Level");
    i02.\u0275\u0275elementEnd()()();
    i02.\u0275\u0275elementStart(28, "div", 53)(29, "label", 63);
    i02.\u0275\u0275text(30, "Description");
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(31, "textarea", 64);
    i02.\u0275\u0275twoWayListener("ngModelChange", function ProjectListPage_Conditional_27_Template_textarea_ngModelChange_31_listener($event) {
      i02.\u0275\u0275restoreView(_r5);
      const ctx_r0 = i02.\u0275\u0275nextContext();
      i02.\u0275\u0275twoWayBindingSet(ctx_r0.newProject.description, $event) || (ctx_r0.newProject.description = $event);
      return i02.\u0275\u0275resetView($event);
    });
    i02.\u0275\u0275elementEnd()();
    i02.\u0275\u0275elementStart(32, "div", 65)(33, "button", 66);
    i02.\u0275\u0275listener("click", function ProjectListPage_Conditional_27_Template_button_click_33_listener() {
      i02.\u0275\u0275restoreView(_r5);
      const ctx_r0 = i02.\u0275\u0275nextContext();
      return i02.\u0275\u0275resetView(ctx_r0.closeCreateDialog());
    });
    i02.\u0275\u0275text(34, "Cancel");
    i02.\u0275\u0275elementEnd();
    i02.\u0275\u0275elementStart(35, "button", 67);
    i02.\u0275\u0275text(36);
    i02.\u0275\u0275elementEnd()()()()();
  }
  if (rf & 2) {
    const ctx_r0 = i02.\u0275\u0275nextContext();
    i02.\u0275\u0275advance(15);
    i02.\u0275\u0275twoWayProperty("ngModel", ctx_r0.newProject.name);
    i02.\u0275\u0275advance(4);
    i02.\u0275\u0275twoWayProperty("ngModel", ctx_r0.newProject.topic);
    i02.\u0275\u0275advance(4);
    i02.\u0275\u0275twoWayProperty("ngModel", ctx_r0.newProject.target_level);
    i02.\u0275\u0275advance(8);
    i02.\u0275\u0275twoWayProperty("ngModel", ctx_r0.newProject.description);
    i02.\u0275\u0275advance(4);
    i02.\u0275\u0275property("disabled", !ctx_r0.newProject.name.trim() || ctx_r0.isCreating);
    i02.\u0275\u0275advance();
    i02.\u0275\u0275textInterpolate1(" ", ctx_r0.isCreating ? "Creating..." : "Create Project", " ");
  }
}
var ProjectListPage = class _ProjectListPage {
  apiService;
  router;
  projects = [];
  masterProjects = [];
  phdProjects = [];
  archivedProjects = [];
  showArchived = false;
  searchQuery = "";
  isLoading = false;
  // Dialog State
  showCreateDialog = false;
  newProject = {
    name: "",
    description: "",
    topic: "",
    target_level: "master"
  };
  isCreating = false;
  constructor(apiService, router) {
    this.apiService = apiService;
    this.router = router;
  }
  ngOnInit() {
    this.loadProjects();
  }
  loadProjects() {
    this.isLoading = true;
    this.apiService.listProjects(this.showArchived).subscribe({
      next: (response) => {
        this.projects = response.projects;
        this.filterAndGroupProjects();
        this.isLoading = false;
      },
      error: (err) => {
        console.error("Failed to load projects", err);
        this.isLoading = false;
      }
    });
  }
  filterAndGroupProjects() {
    let filtered = this.projects;
    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase();
      filtered = filtered.filter((p) => p.name.toLowerCase().includes(q) || p.topic && p.topic.toLowerCase().includes(q) || p.description && p.description.toLowerCase().includes(q));
    }
    if (!this.showArchived) {
      filtered = filtered.filter((p) => !p.is_archived);
      this.archivedProjects = [];
    } else {
      this.archivedProjects = filtered.filter((p) => p.is_archived);
      filtered = filtered.filter((p) => !p.is_archived);
    }
    this.masterProjects = filtered.filter((p) => p.target_level === "master");
    this.phdProjects = filtered.filter((p) => p.target_level === "phd");
  }
  onSearchChange() {
    this.filterAndGroupProjects();
  }
  toggleArchived() {
    this.showArchived = !this.showArchived;
    this.loadProjects();
  }
  openCreateDialog() {
    this.newProject = {
      name: "",
      description: "",
      topic: "",
      target_level: "master"
    };
    this.showCreateDialog = true;
  }
  closeCreateDialog() {
    this.showCreateDialog = false;
  }
  createProject() {
    if (!this.newProject.name.trim())
      return;
    this.isCreating = true;
    this.apiService.createProject(this.newProject).subscribe({
      next: (project) => {
        this.isCreating = false;
        this.closeCreateDialog();
        this.router.navigate(["/projects", project.id]);
      },
      error: (err) => {
        console.error("Failed to create project", err);
        this.isCreating = false;
      }
    });
  }
  static \u0275fac = function ProjectListPage_Factory(__ngFactoryType__) {
    return new (__ngFactoryType__ || _ProjectListPage)(i02.\u0275\u0275directiveInject(ApiService), i02.\u0275\u0275directiveInject(i2.Router));
  };
  static \u0275cmp = /* @__PURE__ */ i02.\u0275\u0275defineComponent({ type: _ProjectListPage, selectors: [["app-project-list"]], decls: 28, vars: 6, consts: [[1, "project-list-layout", "animate-fade-in"], [1, "page-header"], [1, "header-content"], [1, "header-titles"], [1, "text-3xl", "text-primary", "font-bold"], [1, "text-secondary", "mt-1"], [1, "header-actions"], [1, "toggle-switch"], ["type", "checkbox", 3, "change", "checked"], [1, "slider"], [1, "label-text", "text-sm", "text-secondary"], [1, "btn", "btn-primary", 3, "click"], ["xmlns", "http://www.w3.org/2000/svg", "width", "16", "height", "16", "viewBox", "0 0 24 24", "fill", "none", "stroke", "currentColor", "stroke-width", "2", "stroke-linecap", "round", "stroke-linejoin", "round"], ["x1", "12", "y1", "5", "x2", "12", "y2", "19"], ["x1", "5", "y1", "12", "x2", "19", "y2", "12"], [1, "search-bar"], ["xmlns", "http://www.w3.org/2000/svg", "width", "16", "height", "16", "viewBox", "0 0 24 24", "fill", "none", "stroke", "currentColor", "stroke-width", "2", "stroke-linecap", "round", "stroke-linejoin", "round", 1, "search-icon"], ["cx", "11", "cy", "11", "r", "8"], ["x1", "21", "y1", "21", "x2", "16.65", "y2", "16.65"], ["type", "text", "placeholder", "Search projects by name, topic, or description...", 3, "ngModelChange", "input", "ngModel"], ["heading", "No Projects Yet", "description", "Start by creating a new research project to organize your literature review.", "ctaText", "Create Your First Project", 3, "ctaAction"], [1, "loading-state"], [1, "projects-container"], [1, "modal-backdrop", "animate-fade-in"], ["class", "skeleton-card skeleton", 4, "ngFor", "ngForOf"], [1, "skeleton-card", "skeleton"], [1, "project-group"], [1, "project-group", "archived"], [1, "no-results", "text-center", "py-8", "text-secondary"], [1, "group-title", "text-secondary"], [1, "badge", "badge-info"], [1, "project-grid"], [1, "project-card", "card", "glass", 3, "routerLink"], [1, "card-header"], [1, "project-name"], [1, "project-time", "text-xs", "text-muted"], [1, "project-topic", "text-sm", "text-accent"], [1, "project-desc", "text-sm", "text-secondary", "truncate"], [1, "card-footer"], [1, "badge", "badge-success"], [1, "badge", "badge-warning"], [1, "badge"], [1, "project-card", "card", "glass", "opacity-75", 3, "routerLink"], [1, "project-name", "text-muted"], [1, "card-footer", "mt-2"], [1, "modal-container", "card", "glass"], [1, "modal-header"], [1, "text-xl", "font-bold"], [1, "btn", "btn-ghost", "p-1", 3, "click"], ["xmlns", "http://www.w3.org/2000/svg", "width", "20", "height", "20", "viewBox", "0 0 24 24", "fill", "none", "stroke", "currentColor", "stroke-width", "2", "stroke-linecap", "round", "stroke-linejoin", "round"], ["x1", "18", "y1", "6", "x2", "6", "y2", "18"], ["x1", "6", "y1", "6", "x2", "18", "y2", "18"], [1, "modal-body", 3, "ngSubmit"], [1, "form-group"], ["for", "projectName"], [1, "text-error"], ["type", "text", "id", "projectName", "name", "projectName", "required", "", "placeholder", "e.g., LLM Reasoning Capabilities", "autofocus", "", 3, "ngModelChange", "ngModel"], ["for", "projectTopic"], ["type", "text", "id", "projectTopic", "name", "projectTopic", "placeholder", "e.g., Artificial Intelligence", 3, "ngModelChange", "ngModel"], ["for", "targetLevel"], ["id", "targetLevel", "name", "targetLevel", 3, "ngModelChange", "ngModel"], ["value", "master"], ["value", "phd"], ["for", "projectDesc"], ["id", "projectDesc", "name", "projectDesc", "rows", "3", "placeholder", "Brief description of the research goals...", 3, "ngModelChange", "ngModel"], [1, "modal-footer"], ["type", "button", 1, "btn", "btn-ghost", 3, "click"], ["type", "submit", 1, "btn", "btn-primary", 3, "disabled"]], template: function ProjectListPage_Template(rf, ctx) {
    if (rf & 1) {
      i02.\u0275\u0275elementStart(0, "div", 0)(1, "header", 1)(2, "div", 2)(3, "div", 3)(4, "h1", 4);
      i02.\u0275\u0275text(5, "Research Projects");
      i02.\u0275\u0275elementEnd();
      i02.\u0275\u0275elementStart(6, "p", 5);
      i02.\u0275\u0275text(7, "Manage and organize your literature reviews");
      i02.\u0275\u0275elementEnd()();
      i02.\u0275\u0275elementStart(8, "div", 6)(9, "label", 7)(10, "input", 8);
      i02.\u0275\u0275listener("change", function ProjectListPage_Template_input_change_10_listener() {
        return ctx.toggleArchived();
      });
      i02.\u0275\u0275elementEnd();
      i02.\u0275\u0275element(11, "span", 9);
      i02.\u0275\u0275elementStart(12, "span", 10);
      i02.\u0275\u0275text(13, "Show Archived");
      i02.\u0275\u0275elementEnd()();
      i02.\u0275\u0275elementStart(14, "button", 11);
      i02.\u0275\u0275listener("click", function ProjectListPage_Template_button_click_14_listener() {
        return ctx.openCreateDialog();
      });
      i02.\u0275\u0275namespaceSVG();
      i02.\u0275\u0275elementStart(15, "svg", 12);
      i02.\u0275\u0275element(16, "line", 13)(17, "line", 14);
      i02.\u0275\u0275elementEnd();
      i02.\u0275\u0275text(18, " New Project ");
      i02.\u0275\u0275elementEnd()()();
      i02.\u0275\u0275namespaceHTML();
      i02.\u0275\u0275elementStart(19, "div", 15);
      i02.\u0275\u0275namespaceSVG();
      i02.\u0275\u0275elementStart(20, "svg", 16);
      i02.\u0275\u0275element(21, "circle", 17)(22, "line", 18);
      i02.\u0275\u0275elementEnd();
      i02.\u0275\u0275namespaceHTML();
      i02.\u0275\u0275elementStart(23, "input", 19);
      i02.\u0275\u0275twoWayListener("ngModelChange", function ProjectListPage_Template_input_ngModelChange_23_listener($event) {
        i02.\u0275\u0275twoWayBindingSet(ctx.searchQuery, $event) || (ctx.searchQuery = $event);
        return $event;
      });
      i02.\u0275\u0275listener("input", function ProjectListPage_Template_input_input_23_listener() {
        return ctx.onSearchChange();
      });
      i02.\u0275\u0275elementEnd()()();
      i02.\u0275\u0275conditionalCreate(24, ProjectListPage_Conditional_24_Template, 1, 1, "app-empty-state", 20);
      i02.\u0275\u0275conditionalCreate(25, ProjectListPage_Conditional_25_Template, 2, 2, "div", 21);
      i02.\u0275\u0275conditionalCreate(26, ProjectListPage_Conditional_26_Template, 5, 4, "div", 22);
      i02.\u0275\u0275elementEnd();
      i02.\u0275\u0275conditionalCreate(27, ProjectListPage_Conditional_27_Template, 37, 6, "div", 23);
    }
    if (rf & 2) {
      i02.\u0275\u0275advance(10);
      i02.\u0275\u0275property("checked", ctx.showArchived);
      i02.\u0275\u0275advance(13);
      i02.\u0275\u0275twoWayProperty("ngModel", ctx.searchQuery);
      i02.\u0275\u0275advance();
      i02.\u0275\u0275conditional(!ctx.isLoading && ctx.projects.length === 0 ? 24 : -1);
      i02.\u0275\u0275advance();
      i02.\u0275\u0275conditional(ctx.isLoading ? 25 : -1);
      i02.\u0275\u0275advance();
      i02.\u0275\u0275conditional(!ctx.isLoading && ctx.projects.length > 0 ? 26 : -1);
      i02.\u0275\u0275advance();
      i02.\u0275\u0275conditional(ctx.showCreateDialog ? 27 : -1);
    }
  }, dependencies: [CommonModule, i3.NgClass, i3.NgComponentOutlet, i3.NgForOf, i3.NgIf, i3.NgTemplateOutlet, i3.NgStyle, i3.NgSwitch, i3.NgSwitchCase, i3.NgSwitchDefault, i3.NgPlural, i3.NgPluralCase, RouterModule, i2.RouterOutlet, i2.RouterLink, i2.RouterLinkActive, i2.\u0275EmptyOutletComponent, FormsModule, i4.\u0275NgNoValidate, i4.NgSelectOption, i4.\u0275NgSelectMultipleOption, i4.DefaultValueAccessor, i4.NumberValueAccessor, i4.RangeValueAccessor, i4.CheckboxControlValueAccessor, i4.SelectControlValueAccessor, i4.SelectMultipleControlValueAccessor, i4.RadioControlValueAccessor, i4.NgControlStatus, i4.NgControlStatusGroup, i4.RequiredValidator, i4.MinLengthValidator, i4.MaxLengthValidator, i4.PatternValidator, i4.CheckboxRequiredValidator, i4.EmailValidator, i4.MinValidator, i4.MaxValidator, i4.NgModel, i4.NgModelGroup, i4.NgForm, EmptyStateComponent, i3.AsyncPipe, i3.UpperCasePipe, i3.LowerCasePipe, i3.JsonPipe, i3.SlicePipe, i3.DecimalPipe, i3.PercentPipe, i3.TitleCasePipe, i3.CurrencyPipe, i3.DatePipe, i3.I18nPluralPipe, i3.I18nSelectPipe, i3.KeyValuePipe, RelativeTimePipe], styles: ['\n.project-list-layout[_ngcontent-%COMP%] {\n  padding: var(--space-6) var(--space-8);\n  max-width: var(--max-content-width);\n  margin: 0 auto;\n}\n.page-header[_ngcontent-%COMP%] {\n  margin-bottom: var(--space-8);\n}\n.header-content[_ngcontent-%COMP%] {\n  display: flex;\n  justify-content: space-between;\n  align-items: flex-start;\n  margin-bottom: var(--space-6);\n  flex-wrap: wrap;\n  gap: var(--space-4);\n}\n.header-actions[_ngcontent-%COMP%] {\n  display: flex;\n  align-items: center;\n  gap: var(--space-6);\n}\n.toggle-switch[_ngcontent-%COMP%] {\n  display: flex;\n  align-items: center;\n  gap: var(--space-2);\n  cursor: pointer;\n}\n.toggle-switch[_ngcontent-%COMP%]   input[_ngcontent-%COMP%] {\n  display: none;\n}\n.toggle-switch[_ngcontent-%COMP%]   .slider[_ngcontent-%COMP%] {\n  position: relative;\n  width: 36px;\n  height: 20px;\n  background: var(--color-bg-input);\n  border-radius: var(--radius-full);\n  border: 1px solid var(--color-border);\n  transition: var(--transition-fast);\n}\n.toggle-switch[_ngcontent-%COMP%]   .slider[_ngcontent-%COMP%]::before {\n  content: "";\n  position: absolute;\n  top: 2px;\n  left: 2px;\n  width: 14px;\n  height: 14px;\n  background: var(--color-text-muted);\n  border-radius: 50%;\n  transition: var(--transition-fast);\n}\n.toggle-switch[_ngcontent-%COMP%]   input[_ngcontent-%COMP%]:checked    + .slider[_ngcontent-%COMP%] {\n  background: rgba(99, 102, 241, 0.2);\n  border-color: var(--color-accent);\n}\n.toggle-switch[_ngcontent-%COMP%]   input[_ngcontent-%COMP%]:checked    + .slider[_ngcontent-%COMP%]::before {\n  transform: translateX(16px);\n  background: var(--color-accent);\n}\n.search-bar[_ngcontent-%COMP%] {\n  position: relative;\n  max-width: 600px;\n}\n.search-bar[_ngcontent-%COMP%]   .search-icon[_ngcontent-%COMP%] {\n  position: absolute;\n  left: var(--space-4);\n  top: 50%;\n  transform: translateY(-50%);\n  color: var(--color-text-muted);\n}\n.search-bar[_ngcontent-%COMP%]   input[_ngcontent-%COMP%] {\n  padding-left: calc(var(--space-8) + var(--space-2));\n  background: var(--color-bg-card);\n}\n.loading-state[_ngcontent-%COMP%] {\n  display: grid;\n  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));\n  gap: var(--space-6);\n}\n.loading-state[_ngcontent-%COMP%]   .skeleton-card[_ngcontent-%COMP%] {\n  height: 140px;\n}\n.project-group[_ngcontent-%COMP%] {\n  margin-bottom: var(--space-10);\n}\n.project-group[_ngcontent-%COMP%]   .group-title[_ngcontent-%COMP%] {\n  font-size: var(--text-lg);\n  font-weight: 600;\n  margin-bottom: var(--space-4);\n  display: flex;\n  align-items: center;\n  gap: var(--space-3);\n}\n.project-grid[_ngcontent-%COMP%] {\n  display: grid;\n  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));\n  gap: var(--space-6);\n}\n.project-card[_ngcontent-%COMP%] {\n  display: flex;\n  flex-direction: column;\n  padding: var(--space-5);\n  cursor: pointer;\n  text-decoration: none;\n  border-left: 3px solid transparent;\n}\n.project-card[_ngcontent-%COMP%]:hover {\n  border-left-color: var(--color-accent);\n  transform: translateY(-2px);\n}\n.project-card[_ngcontent-%COMP%]   .card-header[_ngcontent-%COMP%] {\n  display: flex;\n  justify-content: space-between;\n  align-items: flex-start;\n  margin-bottom: var(--space-2);\n}\n.project-card[_ngcontent-%COMP%]   .project-name[_ngcontent-%COMP%] {\n  font-weight: 600;\n  font-size: var(--text-base);\n  color: var(--color-text-primary);\n}\n.project-card[_ngcontent-%COMP%]   .project-topic[_ngcontent-%COMP%] {\n  font-weight: 500;\n  margin-bottom: var(--space-2);\n}\n.project-card[_ngcontent-%COMP%]   .project-desc[_ngcontent-%COMP%] {\n  margin-bottom: var(--space-4);\n  flex-grow: 1;\n}\n.project-card[_ngcontent-%COMP%]   .card-footer[_ngcontent-%COMP%] {\n  display: flex;\n  gap: var(--space-2);\n  margin-top: auto;\n}\n.opacity-75[_ngcontent-%COMP%] {\n  opacity: 0.75;\n}\n.modal-backdrop[_ngcontent-%COMP%] {\n  position: fixed;\n  top: 0;\n  left: 0;\n  right: 0;\n  bottom: 0;\n  background: rgba(10, 14, 26, 0.8);\n  -webkit-backdrop-filter: blur(4px);\n  backdrop-filter: blur(4px);\n  z-index: 100;\n  display: flex;\n  align-items: center;\n  justify-content: center;\n  padding: var(--space-4);\n}\n.modal-container[_ngcontent-%COMP%] {\n  width: 100%;\n  max-width: 500px;\n  background: var(--color-bg-tertiary);\n  box-shadow: var(--shadow-lg);\n}\n.modal-header[_ngcontent-%COMP%] {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  padding-bottom: var(--space-4);\n  border-bottom: 1px solid var(--color-border);\n  margin-bottom: var(--space-4);\n}\n.form-group[_ngcontent-%COMP%] {\n  margin-bottom: var(--space-4);\n}\n.form-group[_ngcontent-%COMP%]   label[_ngcontent-%COMP%] {\n  display: block;\n  margin-bottom: var(--space-2);\n  font-weight: 500;\n  color: var(--color-text-secondary);\n  font-size: var(--text-sm);\n}\n.modal-footer[_ngcontent-%COMP%] {\n  display: flex;\n  justify-content: flex-end;\n  gap: var(--space-3);\n  margin-top: var(--space-6);\n  padding-top: var(--space-4);\n  border-top: 1px solid var(--color-border);\n}\n.p-1[_ngcontent-%COMP%] {\n  padding: var(--space-1);\n}\n.mt-1[_ngcontent-%COMP%] {\n  margin-top: var(--space-1);\n}\n.mt-2[_ngcontent-%COMP%] {\n  margin-top: var(--space-2);\n}\n.py-8[_ngcontent-%COMP%] {\n  padding-top: var(--space-8);\n  padding-bottom: var(--space-8);\n}\n.text-center[_ngcontent-%COMP%] {\n  text-align: center;\n}\n.font-bold[_ngcontent-%COMP%] {\n  font-weight: 700;\n}\n/*# sourceMappingURL=project-list.page.css.map */'] });
};
(() => {
  (typeof ngDevMode === "undefined" || ngDevMode) && i02.\u0275setClassMetadata(ProjectListPage, [{
    type: Component,
    args: [{ selector: "app-project-list", standalone: true, imports: [CommonModule, RouterModule, FormsModule, RelativeTimePipe, EmptyStateComponent], template: `<div class="project-list-layout animate-fade-in">
  <!-- Header -->
  <header class="page-header">
    <div class="header-content">
      <div class="header-titles">
        <h1 class="text-3xl text-primary font-bold">Research Projects</h1>
        <p class="text-secondary mt-1">Manage and organize your literature reviews</p>
      </div>
      <div class="header-actions">
        <label class="toggle-switch">
          <input type="checkbox" [checked]="showArchived" (change)="toggleArchived()">
          <span class="slider"></span>
          <span class="label-text text-sm text-secondary">Show Archived</span>
        </label>
        <button class="btn btn-primary" (click)="openCreateDialog()">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
          New Project
        </button>
      </div>
    </div>

    <!-- Search/Filter -->
    <div class="search-bar">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="search-icon"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
      <input type="text" placeholder="Search projects by name, topic, or description..." [(ngModel)]="searchQuery" (input)="onSearchChange()">
    </div>
  </header>

  <!-- Empty State -->
  @if (!isLoading && projects.length === 0) {
    <app-empty-state 
      heading="No Projects Yet" 
      description="Start by creating a new research project to organize your literature review."
      ctaText="Create Your First Project"
      [ctaAction]="openCreateDialog.bind(this)">
    </app-empty-state>
  }

  <!-- Loading State -->
  @if (isLoading) {
    <div class="loading-state">
      <div class="skeleton-card skeleton" *ngFor="let i of [1,2,3]"></div>
    </div>
  }

  <!-- Projects List -->
  @if (!isLoading && projects.length > 0) {
    <div class="projects-container">
      
      <!-- Master Level Projects -->
      @if (masterProjects.length > 0) {
        <section class="project-group">
          <h2 class="group-title text-secondary">Master Level <span class="badge badge-info">{{masterProjects.length}}</span></h2>
          <div class="project-grid">
            @for (project of masterProjects; track project.id) {
              <a [routerLink]="['/projects', project.id]" class="project-card card glass">
                <div class="card-header">
                  <h3 class="project-name">{{ project.name }}</h3>
                  <span class="project-time text-xs text-muted">{{ project.updated_at | relativeTime }}</span>
                </div>
                @if (project.topic) {
                  <p class="project-topic text-sm text-accent">{{ project.topic }}</p>
                }
                @if (project.description) {
                  <p class="project-desc text-sm text-secondary truncate">{{ project.description }}</p>
                }
                <div class="card-footer">
                  <span class="badge badge-success">{{ project.paper_count }} Papers</span>
                  <span class="badge badge-warning">{{ project.question_count }} Questions</span>
                </div>
              </a>
            }
          </div>
        </section>
      }

      <!-- PhD Level Projects -->
      @if (phdProjects.length > 0) {
        <section class="project-group">
          <h2 class="group-title text-secondary">PhD Level <span class="badge badge-info">{{phdProjects.length}}</span></h2>
          <div class="project-grid">
            @for (project of phdProjects; track project.id) {
              <a [routerLink]="['/projects', project.id]" class="project-card card glass">
                <div class="card-header">
                  <h3 class="project-name">{{ project.name }}</h3>
                  <span class="project-time text-xs text-muted">{{ project.updated_at | relativeTime }}</span>
                </div>
                @if (project.topic) {
                  <p class="project-topic text-sm text-accent">{{ project.topic }}</p>
                }
                @if (project.description) {
                  <p class="project-desc text-sm text-secondary truncate">{{ project.description }}</p>
                }
                <div class="card-footer">
                  <span class="badge badge-success">{{ project.paper_count }} Papers</span>
                  <span class="badge badge-warning">{{ project.question_count }} Questions</span>
                </div>
              </a>
            }
          </div>
        </section>
      }

      <!-- Archived Projects -->
      @if (archivedProjects.length > 0) {
        <section class="project-group archived">
          <h2 class="group-title text-secondary">Archived <span class="badge">{{archivedProjects.length}}</span></h2>
          <div class="project-grid">
            @for (project of archivedProjects; track project.id) {
              <a [routerLink]="['/projects', project.id]" class="project-card card glass opacity-75">
                <div class="card-header">
                  <h3 class="project-name text-muted">{{ project.name }}</h3>
                  <span class="project-time text-xs text-muted">{{ project.updated_at | relativeTime }}</span>
                </div>
                <div class="card-footer mt-2">
                  <span class="badge">Archived</span>
                </div>
              </a>
            }
          </div>
        </section>
      }
      
      <!-- No search results -->
      @if (projects.length > 0 && masterProjects.length === 0 && phdProjects.length === 0 && archivedProjects.length === 0) {
        <div class="no-results text-center py-8 text-secondary">
          No projects matching "{{searchQuery}}"
        </div>
      }
    </div>
  }
</div>

<!-- Project Creation Dialog -->
@if (showCreateDialog) {
  <div class="modal-backdrop animate-fade-in">
    <div class="modal-container card glass">
      <div class="modal-header">
        <h2 class="text-xl font-bold">New Project</h2>
        <button class="btn btn-ghost p-1" (click)="closeCreateDialog()">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
      
      <form class="modal-body" (ngSubmit)="createProject()">
        <div class="form-group">
          <label for="projectName">Project Name <span class="text-error">*</span></label>
          <input type="text" id="projectName" name="projectName" [(ngModel)]="newProject.name" required placeholder="e.g., LLM Reasoning Capabilities" autofocus>
        </div>
        
        <div class="form-group">
          <label for="projectTopic">Topic</label>
          <input type="text" id="projectTopic" name="projectTopic" [(ngModel)]="newProject.topic" placeholder="e.g., Artificial Intelligence">
        </div>

        <div class="form-group">
          <label for="targetLevel">Target Level</label>
          <select id="targetLevel" name="targetLevel" [(ngModel)]="newProject.target_level">
            <option value="master">Master Level</option>
            <option value="phd">PhD Level</option>
          </select>
        </div>

        <div class="form-group">
          <label for="projectDesc">Description</label>
          <textarea id="projectDesc" name="projectDesc" [(ngModel)]="newProject.description" rows="3" placeholder="Brief description of the research goals..."></textarea>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-ghost" (click)="closeCreateDialog()">Cancel</button>
          <button type="submit" class="btn btn-primary" [disabled]="!newProject.name.trim() || isCreating">
            {{ isCreating ? 'Creating...' : 'Create Project' }}
          </button>
        </div>
      </form>
    </div>
  </div>
}
`, styles: ['/* src/app/features/projects/project-list/project-list.page.scss */\n.project-list-layout {\n  padding: var(--space-6) var(--space-8);\n  max-width: var(--max-content-width);\n  margin: 0 auto;\n}\n.page-header {\n  margin-bottom: var(--space-8);\n}\n.header-content {\n  display: flex;\n  justify-content: space-between;\n  align-items: flex-start;\n  margin-bottom: var(--space-6);\n  flex-wrap: wrap;\n  gap: var(--space-4);\n}\n.header-actions {\n  display: flex;\n  align-items: center;\n  gap: var(--space-6);\n}\n.toggle-switch {\n  display: flex;\n  align-items: center;\n  gap: var(--space-2);\n  cursor: pointer;\n}\n.toggle-switch input {\n  display: none;\n}\n.toggle-switch .slider {\n  position: relative;\n  width: 36px;\n  height: 20px;\n  background: var(--color-bg-input);\n  border-radius: var(--radius-full);\n  border: 1px solid var(--color-border);\n  transition: var(--transition-fast);\n}\n.toggle-switch .slider::before {\n  content: "";\n  position: absolute;\n  top: 2px;\n  left: 2px;\n  width: 14px;\n  height: 14px;\n  background: var(--color-text-muted);\n  border-radius: 50%;\n  transition: var(--transition-fast);\n}\n.toggle-switch input:checked + .slider {\n  background: rgba(99, 102, 241, 0.2);\n  border-color: var(--color-accent);\n}\n.toggle-switch input:checked + .slider::before {\n  transform: translateX(16px);\n  background: var(--color-accent);\n}\n.search-bar {\n  position: relative;\n  max-width: 600px;\n}\n.search-bar .search-icon {\n  position: absolute;\n  left: var(--space-4);\n  top: 50%;\n  transform: translateY(-50%);\n  color: var(--color-text-muted);\n}\n.search-bar input {\n  padding-left: calc(var(--space-8) + var(--space-2));\n  background: var(--color-bg-card);\n}\n.loading-state {\n  display: grid;\n  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));\n  gap: var(--space-6);\n}\n.loading-state .skeleton-card {\n  height: 140px;\n}\n.project-group {\n  margin-bottom: var(--space-10);\n}\n.project-group .group-title {\n  font-size: var(--text-lg);\n  font-weight: 600;\n  margin-bottom: var(--space-4);\n  display: flex;\n  align-items: center;\n  gap: var(--space-3);\n}\n.project-grid {\n  display: grid;\n  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));\n  gap: var(--space-6);\n}\n.project-card {\n  display: flex;\n  flex-direction: column;\n  padding: var(--space-5);\n  cursor: pointer;\n  text-decoration: none;\n  border-left: 3px solid transparent;\n}\n.project-card:hover {\n  border-left-color: var(--color-accent);\n  transform: translateY(-2px);\n}\n.project-card .card-header {\n  display: flex;\n  justify-content: space-between;\n  align-items: flex-start;\n  margin-bottom: var(--space-2);\n}\n.project-card .project-name {\n  font-weight: 600;\n  font-size: var(--text-base);\n  color: var(--color-text-primary);\n}\n.project-card .project-topic {\n  font-weight: 500;\n  margin-bottom: var(--space-2);\n}\n.project-card .project-desc {\n  margin-bottom: var(--space-4);\n  flex-grow: 1;\n}\n.project-card .card-footer {\n  display: flex;\n  gap: var(--space-2);\n  margin-top: auto;\n}\n.opacity-75 {\n  opacity: 0.75;\n}\n.modal-backdrop {\n  position: fixed;\n  top: 0;\n  left: 0;\n  right: 0;\n  bottom: 0;\n  background: rgba(10, 14, 26, 0.8);\n  -webkit-backdrop-filter: blur(4px);\n  backdrop-filter: blur(4px);\n  z-index: 100;\n  display: flex;\n  align-items: center;\n  justify-content: center;\n  padding: var(--space-4);\n}\n.modal-container {\n  width: 100%;\n  max-width: 500px;\n  background: var(--color-bg-tertiary);\n  box-shadow: var(--shadow-lg);\n}\n.modal-header {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  padding-bottom: var(--space-4);\n  border-bottom: 1px solid var(--color-border);\n  margin-bottom: var(--space-4);\n}\n.form-group {\n  margin-bottom: var(--space-4);\n}\n.form-group label {\n  display: block;\n  margin-bottom: var(--space-2);\n  font-weight: 500;\n  color: var(--color-text-secondary);\n  font-size: var(--text-sm);\n}\n.modal-footer {\n  display: flex;\n  justify-content: flex-end;\n  gap: var(--space-3);\n  margin-top: var(--space-6);\n  padding-top: var(--space-4);\n  border-top: 1px solid var(--color-border);\n}\n.p-1 {\n  padding: var(--space-1);\n}\n.mt-1 {\n  margin-top: var(--space-1);\n}\n.mt-2 {\n  margin-top: var(--space-2);\n}\n.py-8 {\n  padding-top: var(--space-8);\n  padding-bottom: var(--space-8);\n}\n.text-center {\n  text-align: center;\n}\n.font-bold {\n  font-weight: 700;\n}\n/*# sourceMappingURL=project-list.page.css.map */\n'] }]
  }], () => [{ type: ApiService }, { type: i2.Router }], null);
})();
(() => {
  (typeof ngDevMode === "undefined" || ngDevMode) && i02.\u0275setClassDebugInfo(ProjectListPage, { className: "ProjectListPage", filePath: "src/app/features/projects/project-list/project-list.page.ts", lineNumber: 16 });
})();
(() => {
  const id = "src%2Fapp%2Ffeatures%2Fprojects%2Fproject-list%2Fproject-list.page.ts%40ProjectListPage";
  function ProjectListPage_HmrLoad(t) {
    import(
      /* @vite-ignore */
      __vite__injectQuery(i02.\u0275\u0275getReplaceMetadataURL(id, t, import.meta.url), 'import')
    ).then((m) => m.default && i02.\u0275\u0275replaceMetadata(ProjectListPage, m.default, [i02, i3, i2, i4, api_service_exports], [CommonModule, RouterModule, FormsModule, EmptyStateComponent, RelativeTimePipe, Component], import.meta, id));
  }
  (typeof ngDevMode === "undefined" || ngDevMode) && ProjectListPage_HmrLoad(Date.now());
  (typeof ngDevMode === "undefined" || ngDevMode) && (import.meta.hot && import.meta.hot.on("angular:component-update", (d) => d.id === id && ProjectListPage_HmrLoad(d.timestamp)));
})();
export {
  ProjectListPage
};


//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbInNyYy9hcHAvZmVhdHVyZXMvcHJvamVjdHMvcHJvamVjdC1saXN0L3Byb2plY3QtbGlzdC5wYWdlLnRzIiwic3JjL2FwcC9mZWF0dXJlcy9wcm9qZWN0cy9wcm9qZWN0LWxpc3QvcHJvamVjdC1saXN0LnBhZ2UuaHRtbCIsInNyYy9hcHAvc2hhcmVkL3JlbGF0aXZlLXRpbWUucGlwZS50cyJdLCJzb3VyY2VzQ29udGVudCI6WyJpbXBvcnQgeyBDb21wb25lbnQsIE9uSW5pdCB9IGZyb20gJ0Bhbmd1bGFyL2NvcmUnO1xuaW1wb3J0IHsgQ29tbW9uTW9kdWxlIH0gZnJvbSAnQGFuZ3VsYXIvY29tbW9uJztcbmltcG9ydCB7IFJvdXRlciwgUm91dGVyTW9kdWxlIH0gZnJvbSAnQGFuZ3VsYXIvcm91dGVyJztcbmltcG9ydCB7IEZvcm1zTW9kdWxlIH0gZnJvbSAnQGFuZ3VsYXIvZm9ybXMnO1xuaW1wb3J0IHsgQXBpU2VydmljZSwgUHJvamVjdCwgUHJvamVjdENyZWF0ZVJlcXVlc3QgfSBmcm9tICcuLi8uLi8uLi9jb3JlL2FwaS5zZXJ2aWNlJztcbmltcG9ydCB7IFJlbGF0aXZlVGltZVBpcGUgfSBmcm9tICcuLi8uLi8uLi9zaGFyZWQvcmVsYXRpdmUtdGltZS5waXBlJztcbmltcG9ydCB7IEVtcHR5U3RhdGVDb21wb25lbnQgfSBmcm9tICcuLi8uLi8uLi9zaGFyZWQvZW1wdHktc3RhdGUvZW1wdHktc3RhdGUuY29tcG9uZW50JztcblxuQENvbXBvbmVudCh7XG4gIHNlbGVjdG9yOiAnYXBwLXByb2plY3QtbGlzdCcsXG4gIHN0YW5kYWxvbmU6IHRydWUsXG4gIGltcG9ydHM6IFtDb21tb25Nb2R1bGUsIFJvdXRlck1vZHVsZSwgRm9ybXNNb2R1bGUsIFJlbGF0aXZlVGltZVBpcGUsIEVtcHR5U3RhdGVDb21wb25lbnRdLFxuICB0ZW1wbGF0ZVVybDogJy4vcHJvamVjdC1saXN0LnBhZ2UuaHRtbCcsXG4gIHN0eWxlVXJsczogWycuL3Byb2plY3QtbGlzdC5wYWdlLnNjc3MnXVxufSlcbmV4cG9ydCBjbGFzcyBQcm9qZWN0TGlzdFBhZ2UgaW1wbGVtZW50cyBPbkluaXQge1xuICBwcm9qZWN0czogUHJvamVjdFtdID0gW107XG4gIG1hc3RlclByb2plY3RzOiBQcm9qZWN0W10gPSBbXTtcbiAgcGhkUHJvamVjdHM6IFByb2plY3RbXSA9IFtdO1xuICBhcmNoaXZlZFByb2plY3RzOiBQcm9qZWN0W10gPSBbXTtcbiAgXG4gIHNob3dBcmNoaXZlZCA9IGZhbHNlO1xuICBzZWFyY2hRdWVyeSA9ICcnO1xuICBpc0xvYWRpbmcgPSBmYWxzZTtcblxuICAvLyBEaWFsb2cgU3RhdGVcbiAgc2hvd0NyZWF0ZURpYWxvZyA9IGZhbHNlO1xuICBuZXdQcm9qZWN0OiBQcm9qZWN0Q3JlYXRlUmVxdWVzdCA9IHtcbiAgICBuYW1lOiAnJyxcbiAgICBkZXNjcmlwdGlvbjogJycsXG4gICAgdG9waWM6ICcnLFxuICAgIHRhcmdldF9sZXZlbDogJ21hc3RlcidcbiAgfTtcbiAgaXNDcmVhdGluZyA9IGZhbHNlO1xuXG4gIGNvbnN0cnVjdG9yKHByaXZhdGUgYXBpU2VydmljZTogQXBpU2VydmljZSwgcHJpdmF0ZSByb3V0ZXI6IFJvdXRlcikge31cblxuICBuZ09uSW5pdCgpIHtcbiAgICB0aGlzLmxvYWRQcm9qZWN0cygpO1xuICB9XG5cbiAgbG9hZFByb2plY3RzKCkge1xuICAgIHRoaXMuaXNMb2FkaW5nID0gdHJ1ZTtcbiAgICB0aGlzLmFwaVNlcnZpY2UubGlzdFByb2plY3RzKHRoaXMuc2hvd0FyY2hpdmVkKS5zdWJzY3JpYmUoe1xuICAgICAgbmV4dDogKHJlc3BvbnNlKSA9PiB7XG4gICAgICAgIHRoaXMucHJvamVjdHMgPSByZXNwb25zZS5wcm9qZWN0cztcbiAgICAgICAgdGhpcy5maWx0ZXJBbmRHcm91cFByb2plY3RzKCk7XG4gICAgICAgIHRoaXMuaXNMb2FkaW5nID0gZmFsc2U7XG4gICAgICB9LFxuICAgICAgZXJyb3I6IChlcnIpID0+IHtcbiAgICAgICAgY29uc29sZS5lcnJvcignRmFpbGVkIHRvIGxvYWQgcHJvamVjdHMnLCBlcnIpO1xuICAgICAgICB0aGlzLmlzTG9hZGluZyA9IGZhbHNlO1xuICAgICAgfVxuICAgIH0pO1xuICB9XG5cbiAgZmlsdGVyQW5kR3JvdXBQcm9qZWN0cygpIHtcbiAgICBsZXQgZmlsdGVyZWQgPSB0aGlzLnByb2plY3RzO1xuICAgIFxuICAgIGlmICh0aGlzLnNlYXJjaFF1ZXJ5LnRyaW0oKSkge1xuICAgICAgY29uc3QgcSA9IHRoaXMuc2VhcmNoUXVlcnkudG9Mb3dlckNhc2UoKTtcbiAgICAgIGZpbHRlcmVkID0gZmlsdGVyZWQuZmlsdGVyKHAgPT4gXG4gICAgICAgIHAubmFtZS50b0xvd2VyQ2FzZSgpLmluY2x1ZGVzKHEpIHx8IFxuICAgICAgICAocC50b3BpYyAmJiBwLnRvcGljLnRvTG93ZXJDYXNlKCkuaW5jbHVkZXMocSkpIHx8XG4gICAgICAgIChwLmRlc2NyaXB0aW9uICYmIHAuZGVzY3JpcHRpb24udG9Mb3dlckNhc2UoKS5pbmNsdWRlcyhxKSlcbiAgICAgICk7XG4gICAgfVxuXG4gICAgaWYgKCF0aGlzLnNob3dBcmNoaXZlZCkge1xuICAgICAgZmlsdGVyZWQgPSBmaWx0ZXJlZC5maWx0ZXIocCA9PiAhcC5pc19hcmNoaXZlZCk7XG4gICAgICB0aGlzLmFyY2hpdmVkUHJvamVjdHMgPSBbXTtcbiAgICB9IGVsc2Uge1xuICAgICAgdGhpcy5hcmNoaXZlZFByb2plY3RzID0gZmlsdGVyZWQuZmlsdGVyKHAgPT4gcC5pc19hcmNoaXZlZCk7XG4gICAgICBmaWx0ZXJlZCA9IGZpbHRlcmVkLmZpbHRlcihwID0+ICFwLmlzX2FyY2hpdmVkKTtcbiAgICB9XG5cbiAgICB0aGlzLm1hc3RlclByb2plY3RzID0gZmlsdGVyZWQuZmlsdGVyKHAgPT4gcC50YXJnZXRfbGV2ZWwgPT09ICdtYXN0ZXInKTtcbiAgICB0aGlzLnBoZFByb2plY3RzID0gZmlsdGVyZWQuZmlsdGVyKHAgPT4gcC50YXJnZXRfbGV2ZWwgPT09ICdwaGQnKTtcbiAgfVxuXG4gIG9uU2VhcmNoQ2hhbmdlKCkge1xuICAgIHRoaXMuZmlsdGVyQW5kR3JvdXBQcm9qZWN0cygpO1xuICB9XG5cbiAgdG9nZ2xlQXJjaGl2ZWQoKSB7XG4gICAgdGhpcy5zaG93QXJjaGl2ZWQgPSAhdGhpcy5zaG93QXJjaGl2ZWQ7XG4gICAgdGhpcy5sb2FkUHJvamVjdHMoKTtcbiAgfVxuXG4gIG9wZW5DcmVhdGVEaWFsb2coKSB7XG4gICAgdGhpcy5uZXdQcm9qZWN0ID0ge1xuICAgICAgbmFtZTogJycsXG4gICAgICBkZXNjcmlwdGlvbjogJycsXG4gICAgICB0b3BpYzogJycsXG4gICAgICB0YXJnZXRfbGV2ZWw6ICdtYXN0ZXInXG4gICAgfTtcbiAgICB0aGlzLnNob3dDcmVhdGVEaWFsb2cgPSB0cnVlO1xuICB9XG5cbiAgY2xvc2VDcmVhdGVEaWFsb2coKSB7XG4gICAgdGhpcy5zaG93Q3JlYXRlRGlhbG9nID0gZmFsc2U7XG4gIH1cblxuICBjcmVhdGVQcm9qZWN0KCkge1xuICAgIGlmICghdGhpcy5uZXdQcm9qZWN0Lm5hbWUudHJpbSgpKSByZXR1cm47XG5cbiAgICB0aGlzLmlzQ3JlYXRpbmcgPSB0cnVlO1xuICAgIHRoaXMuYXBpU2VydmljZS5jcmVhdGVQcm9qZWN0KHRoaXMubmV3UHJvamVjdCkuc3Vic2NyaWJlKHtcbiAgICAgIG5leHQ6IChwcm9qZWN0KSA9PiB7XG4gICAgICAgIHRoaXMuaXNDcmVhdGluZyA9IGZhbHNlO1xuICAgICAgICB0aGlzLmNsb3NlQ3JlYXRlRGlhbG9nKCk7XG4gICAgICAgIHRoaXMucm91dGVyLm5hdmlnYXRlKFsnL3Byb2plY3RzJywgcHJvamVjdC5pZF0pO1xuICAgICAgfSxcbiAgICAgIGVycm9yOiAoZXJyKSA9PiB7XG4gICAgICAgIGNvbnNvbGUuZXJyb3IoJ0ZhaWxlZCB0byBjcmVhdGUgcHJvamVjdCcsIGVycik7XG4gICAgICAgIHRoaXMuaXNDcmVhdGluZyA9IGZhbHNlO1xuICAgICAgfVxuICAgIH0pO1xuICB9XG59XG4iLCI8ZGl2IGNsYXNzPVwicHJvamVjdC1saXN0LWxheW91dCBhbmltYXRlLWZhZGUtaW5cIj5cbiAgPCEtLSBIZWFkZXIgLS0+XG4gIDxoZWFkZXIgY2xhc3M9XCJwYWdlLWhlYWRlclwiPlxuICAgIDxkaXYgY2xhc3M9XCJoZWFkZXItY29udGVudFwiPlxuICAgICAgPGRpdiBjbGFzcz1cImhlYWRlci10aXRsZXNcIj5cbiAgICAgICAgPGgxIGNsYXNzPVwidGV4dC0zeGwgdGV4dC1wcmltYXJ5IGZvbnQtYm9sZFwiPlJlc2VhcmNoIFByb2plY3RzPC9oMT5cbiAgICAgICAgPHAgY2xhc3M9XCJ0ZXh0LXNlY29uZGFyeSBtdC0xXCI+TWFuYWdlIGFuZCBvcmdhbml6ZSB5b3VyIGxpdGVyYXR1cmUgcmV2aWV3czwvcD5cbiAgICAgIDwvZGl2PlxuICAgICAgPGRpdiBjbGFzcz1cImhlYWRlci1hY3Rpb25zXCI+XG4gICAgICAgIDxsYWJlbCBjbGFzcz1cInRvZ2dsZS1zd2l0Y2hcIj5cbiAgICAgICAgICA8aW5wdXQgdHlwZT1cImNoZWNrYm94XCIgW2NoZWNrZWRdPVwic2hvd0FyY2hpdmVkXCIgKGNoYW5nZSk9XCJ0b2dnbGVBcmNoaXZlZCgpXCI+XG4gICAgICAgICAgPHNwYW4gY2xhc3M9XCJzbGlkZXJcIj48L3NwYW4+XG4gICAgICAgICAgPHNwYW4gY2xhc3M9XCJsYWJlbC10ZXh0IHRleHQtc20gdGV4dC1zZWNvbmRhcnlcIj5TaG93IEFyY2hpdmVkPC9zcGFuPlxuICAgICAgICA8L2xhYmVsPlxuICAgICAgICA8YnV0dG9uIGNsYXNzPVwiYnRuIGJ0bi1wcmltYXJ5XCIgKGNsaWNrKT1cIm9wZW5DcmVhdGVEaWFsb2coKVwiPlxuICAgICAgICAgIDxzdmcgeG1sbnM9XCJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2Z1wiIHdpZHRoPVwiMTZcIiBoZWlnaHQ9XCIxNlwiIHZpZXdCb3g9XCIwIDAgMjQgMjRcIiBmaWxsPVwibm9uZVwiIHN0cm9rZT1cImN1cnJlbnRDb2xvclwiIHN0cm9rZS13aWR0aD1cIjJcIiBzdHJva2UtbGluZWNhcD1cInJvdW5kXCIgc3Ryb2tlLWxpbmVqb2luPVwicm91bmRcIj48bGluZSB4MT1cIjEyXCIgeTE9XCI1XCIgeDI9XCIxMlwiIHkyPVwiMTlcIj48L2xpbmU+PGxpbmUgeDE9XCI1XCIgeTE9XCIxMlwiIHgyPVwiMTlcIiB5Mj1cIjEyXCI+PC9saW5lPjwvc3ZnPlxuICAgICAgICAgIE5ldyBQcm9qZWN0XG4gICAgICAgIDwvYnV0dG9uPlxuICAgICAgPC9kaXY+XG4gICAgPC9kaXY+XG5cbiAgICA8IS0tIFNlYXJjaC9GaWx0ZXIgLS0+XG4gICAgPGRpdiBjbGFzcz1cInNlYXJjaC1iYXJcIj5cbiAgICAgIDxzdmcgeG1sbnM9XCJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2Z1wiIHdpZHRoPVwiMTZcIiBoZWlnaHQ9XCIxNlwiIHZpZXdCb3g9XCIwIDAgMjQgMjRcIiBmaWxsPVwibm9uZVwiIHN0cm9rZT1cImN1cnJlbnRDb2xvclwiIHN0cm9rZS13aWR0aD1cIjJcIiBzdHJva2UtbGluZWNhcD1cInJvdW5kXCIgc3Ryb2tlLWxpbmVqb2luPVwicm91bmRcIiBjbGFzcz1cInNlYXJjaC1pY29uXCI+PGNpcmNsZSBjeD1cIjExXCIgY3k9XCIxMVwiIHI9XCI4XCI+PC9jaXJjbGU+PGxpbmUgeDE9XCIyMVwiIHkxPVwiMjFcIiB4Mj1cIjE2LjY1XCIgeTI9XCIxNi42NVwiPjwvbGluZT48L3N2Zz5cbiAgICAgIDxpbnB1dCB0eXBlPVwidGV4dFwiIHBsYWNlaG9sZGVyPVwiU2VhcmNoIHByb2plY3RzIGJ5IG5hbWUsIHRvcGljLCBvciBkZXNjcmlwdGlvbi4uLlwiIFsobmdNb2RlbCldPVwic2VhcmNoUXVlcnlcIiAoaW5wdXQpPVwib25TZWFyY2hDaGFuZ2UoKVwiPlxuICAgIDwvZGl2PlxuICA8L2hlYWRlcj5cblxuICA8IS0tIEVtcHR5IFN0YXRlIC0tPlxuICBAaWYgKCFpc0xvYWRpbmcgJiYgcHJvamVjdHMubGVuZ3RoID09PSAwKSB7XG4gICAgPGFwcC1lbXB0eS1zdGF0ZSBcbiAgICAgIGhlYWRpbmc9XCJObyBQcm9qZWN0cyBZZXRcIiBcbiAgICAgIGRlc2NyaXB0aW9uPVwiU3RhcnQgYnkgY3JlYXRpbmcgYSBuZXcgcmVzZWFyY2ggcHJvamVjdCB0byBvcmdhbml6ZSB5b3VyIGxpdGVyYXR1cmUgcmV2aWV3LlwiXG4gICAgICBjdGFUZXh0PVwiQ3JlYXRlIFlvdXIgRmlyc3QgUHJvamVjdFwiXG4gICAgICBbY3RhQWN0aW9uXT1cIm9wZW5DcmVhdGVEaWFsb2cuYmluZCh0aGlzKVwiPlxuICAgIDwvYXBwLWVtcHR5LXN0YXRlPlxuICB9XG5cbiAgPCEtLSBMb2FkaW5nIFN0YXRlIC0tPlxuICBAaWYgKGlzTG9hZGluZykge1xuICAgIDxkaXYgY2xhc3M9XCJsb2FkaW5nLXN0YXRlXCI+XG4gICAgICA8ZGl2IGNsYXNzPVwic2tlbGV0b24tY2FyZCBza2VsZXRvblwiICpuZ0Zvcj1cImxldCBpIG9mIFsxLDIsM11cIj48L2Rpdj5cbiAgICA8L2Rpdj5cbiAgfVxuXG4gIDwhLS0gUHJvamVjdHMgTGlzdCAtLT5cbiAgQGlmICghaXNMb2FkaW5nICYmIHByb2plY3RzLmxlbmd0aCA+IDApIHtcbiAgICA8ZGl2IGNsYXNzPVwicHJvamVjdHMtY29udGFpbmVyXCI+XG4gICAgICBcbiAgICAgIDwhLS0gTWFzdGVyIExldmVsIFByb2plY3RzIC0tPlxuICAgICAgQGlmIChtYXN0ZXJQcm9qZWN0cy5sZW5ndGggPiAwKSB7XG4gICAgICAgIDxzZWN0aW9uIGNsYXNzPVwicHJvamVjdC1ncm91cFwiPlxuICAgICAgICAgIDxoMiBjbGFzcz1cImdyb3VwLXRpdGxlIHRleHQtc2Vjb25kYXJ5XCI+TWFzdGVyIExldmVsIDxzcGFuIGNsYXNzPVwiYmFkZ2UgYmFkZ2UtaW5mb1wiPnt7bWFzdGVyUHJvamVjdHMubGVuZ3RofX08L3NwYW4+PC9oMj5cbiAgICAgICAgICA8ZGl2IGNsYXNzPVwicHJvamVjdC1ncmlkXCI+XG4gICAgICAgICAgICBAZm9yIChwcm9qZWN0IG9mIG1hc3RlclByb2plY3RzOyB0cmFjayBwcm9qZWN0LmlkKSB7XG4gICAgICAgICAgICAgIDxhIFtyb3V0ZXJMaW5rXT1cIlsnL3Byb2plY3RzJywgcHJvamVjdC5pZF1cIiBjbGFzcz1cInByb2plY3QtY2FyZCBjYXJkIGdsYXNzXCI+XG4gICAgICAgICAgICAgICAgPGRpdiBjbGFzcz1cImNhcmQtaGVhZGVyXCI+XG4gICAgICAgICAgICAgICAgICA8aDMgY2xhc3M9XCJwcm9qZWN0LW5hbWVcIj57eyBwcm9qZWN0Lm5hbWUgfX08L2gzPlxuICAgICAgICAgICAgICAgICAgPHNwYW4gY2xhc3M9XCJwcm9qZWN0LXRpbWUgdGV4dC14cyB0ZXh0LW11dGVkXCI+e3sgcHJvamVjdC51cGRhdGVkX2F0IHwgcmVsYXRpdmVUaW1lIH19PC9zcGFuPlxuICAgICAgICAgICAgICAgIDwvZGl2PlxuICAgICAgICAgICAgICAgIEBpZiAocHJvamVjdC50b3BpYykge1xuICAgICAgICAgICAgICAgICAgPHAgY2xhc3M9XCJwcm9qZWN0LXRvcGljIHRleHQtc20gdGV4dC1hY2NlbnRcIj57eyBwcm9qZWN0LnRvcGljIH19PC9wPlxuICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICBAaWYgKHByb2plY3QuZGVzY3JpcHRpb24pIHtcbiAgICAgICAgICAgICAgICAgIDxwIGNsYXNzPVwicHJvamVjdC1kZXNjIHRleHQtc20gdGV4dC1zZWNvbmRhcnkgdHJ1bmNhdGVcIj57eyBwcm9qZWN0LmRlc2NyaXB0aW9uIH19PC9wPlxuICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICA8ZGl2IGNsYXNzPVwiY2FyZC1mb290ZXJcIj5cbiAgICAgICAgICAgICAgICAgIDxzcGFuIGNsYXNzPVwiYmFkZ2UgYmFkZ2Utc3VjY2Vzc1wiPnt7IHByb2plY3QucGFwZXJfY291bnQgfX0gUGFwZXJzPC9zcGFuPlxuICAgICAgICAgICAgICAgICAgPHNwYW4gY2xhc3M9XCJiYWRnZSBiYWRnZS13YXJuaW5nXCI+e3sgcHJvamVjdC5xdWVzdGlvbl9jb3VudCB9fSBRdWVzdGlvbnM8L3NwYW4+XG4gICAgICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgICAgICAgIDwvYT5cbiAgICAgICAgICAgIH1cbiAgICAgICAgICA8L2Rpdj5cbiAgICAgICAgPC9zZWN0aW9uPlxuICAgICAgfVxuXG4gICAgICA8IS0tIFBoRCBMZXZlbCBQcm9qZWN0cyAtLT5cbiAgICAgIEBpZiAocGhkUHJvamVjdHMubGVuZ3RoID4gMCkge1xuICAgICAgICA8c2VjdGlvbiBjbGFzcz1cInByb2plY3QtZ3JvdXBcIj5cbiAgICAgICAgICA8aDIgY2xhc3M9XCJncm91cC10aXRsZSB0ZXh0LXNlY29uZGFyeVwiPlBoRCBMZXZlbCA8c3BhbiBjbGFzcz1cImJhZGdlIGJhZGdlLWluZm9cIj57e3BoZFByb2plY3RzLmxlbmd0aH19PC9zcGFuPjwvaDI+XG4gICAgICAgICAgPGRpdiBjbGFzcz1cInByb2plY3QtZ3JpZFwiPlxuICAgICAgICAgICAgQGZvciAocHJvamVjdCBvZiBwaGRQcm9qZWN0czsgdHJhY2sgcHJvamVjdC5pZCkge1xuICAgICAgICAgICAgICA8YSBbcm91dGVyTGlua109XCJbJy9wcm9qZWN0cycsIHByb2plY3QuaWRdXCIgY2xhc3M9XCJwcm9qZWN0LWNhcmQgY2FyZCBnbGFzc1wiPlxuICAgICAgICAgICAgICAgIDxkaXYgY2xhc3M9XCJjYXJkLWhlYWRlclwiPlxuICAgICAgICAgICAgICAgICAgPGgzIGNsYXNzPVwicHJvamVjdC1uYW1lXCI+e3sgcHJvamVjdC5uYW1lIH19PC9oMz5cbiAgICAgICAgICAgICAgICAgIDxzcGFuIGNsYXNzPVwicHJvamVjdC10aW1lIHRleHQteHMgdGV4dC1tdXRlZFwiPnt7IHByb2plY3QudXBkYXRlZF9hdCB8IHJlbGF0aXZlVGltZSB9fTwvc3Bhbj5cbiAgICAgICAgICAgICAgICA8L2Rpdj5cbiAgICAgICAgICAgICAgICBAaWYgKHByb2plY3QudG9waWMpIHtcbiAgICAgICAgICAgICAgICAgIDxwIGNsYXNzPVwicHJvamVjdC10b3BpYyB0ZXh0LXNtIHRleHQtYWNjZW50XCI+e3sgcHJvamVjdC50b3BpYyB9fTwvcD5cbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICAgICAgQGlmIChwcm9qZWN0LmRlc2NyaXB0aW9uKSB7XG4gICAgICAgICAgICAgICAgICA8cCBjbGFzcz1cInByb2plY3QtZGVzYyB0ZXh0LXNtIHRleHQtc2Vjb25kYXJ5IHRydW5jYXRlXCI+e3sgcHJvamVjdC5kZXNjcmlwdGlvbiB9fTwvcD5cbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICAgICAgPGRpdiBjbGFzcz1cImNhcmQtZm9vdGVyXCI+XG4gICAgICAgICAgICAgICAgICA8c3BhbiBjbGFzcz1cImJhZGdlIGJhZGdlLXN1Y2Nlc3NcIj57eyBwcm9qZWN0LnBhcGVyX2NvdW50IH19IFBhcGVyczwvc3Bhbj5cbiAgICAgICAgICAgICAgICAgIDxzcGFuIGNsYXNzPVwiYmFkZ2UgYmFkZ2Utd2FybmluZ1wiPnt7IHByb2plY3QucXVlc3Rpb25fY291bnQgfX0gUXVlc3Rpb25zPC9zcGFuPlxuICAgICAgICAgICAgICAgIDwvZGl2PlxuICAgICAgICAgICAgICA8L2E+XG4gICAgICAgICAgICB9XG4gICAgICAgICAgPC9kaXY+XG4gICAgICAgIDwvc2VjdGlvbj5cbiAgICAgIH1cblxuICAgICAgPCEtLSBBcmNoaXZlZCBQcm9qZWN0cyAtLT5cbiAgICAgIEBpZiAoYXJjaGl2ZWRQcm9qZWN0cy5sZW5ndGggPiAwKSB7XG4gICAgICAgIDxzZWN0aW9uIGNsYXNzPVwicHJvamVjdC1ncm91cCBhcmNoaXZlZFwiPlxuICAgICAgICAgIDxoMiBjbGFzcz1cImdyb3VwLXRpdGxlIHRleHQtc2Vjb25kYXJ5XCI+QXJjaGl2ZWQgPHNwYW4gY2xhc3M9XCJiYWRnZVwiPnt7YXJjaGl2ZWRQcm9qZWN0cy5sZW5ndGh9fTwvc3Bhbj48L2gyPlxuICAgICAgICAgIDxkaXYgY2xhc3M9XCJwcm9qZWN0LWdyaWRcIj5cbiAgICAgICAgICAgIEBmb3IgKHByb2plY3Qgb2YgYXJjaGl2ZWRQcm9qZWN0czsgdHJhY2sgcHJvamVjdC5pZCkge1xuICAgICAgICAgICAgICA8YSBbcm91dGVyTGlua109XCJbJy9wcm9qZWN0cycsIHByb2plY3QuaWRdXCIgY2xhc3M9XCJwcm9qZWN0LWNhcmQgY2FyZCBnbGFzcyBvcGFjaXR5LTc1XCI+XG4gICAgICAgICAgICAgICAgPGRpdiBjbGFzcz1cImNhcmQtaGVhZGVyXCI+XG4gICAgICAgICAgICAgICAgICA8aDMgY2xhc3M9XCJwcm9qZWN0LW5hbWUgdGV4dC1tdXRlZFwiPnt7IHByb2plY3QubmFtZSB9fTwvaDM+XG4gICAgICAgICAgICAgICAgICA8c3BhbiBjbGFzcz1cInByb2plY3QtdGltZSB0ZXh0LXhzIHRleHQtbXV0ZWRcIj57eyBwcm9qZWN0LnVwZGF0ZWRfYXQgfCByZWxhdGl2ZVRpbWUgfX08L3NwYW4+XG4gICAgICAgICAgICAgICAgPC9kaXY+XG4gICAgICAgICAgICAgICAgPGRpdiBjbGFzcz1cImNhcmQtZm9vdGVyIG10LTJcIj5cbiAgICAgICAgICAgICAgICAgIDxzcGFuIGNsYXNzPVwiYmFkZ2VcIj5BcmNoaXZlZDwvc3Bhbj5cbiAgICAgICAgICAgICAgICA8L2Rpdj5cbiAgICAgICAgICAgICAgPC9hPlxuICAgICAgICAgICAgfVxuICAgICAgICAgIDwvZGl2PlxuICAgICAgICA8L3NlY3Rpb24+XG4gICAgICB9XG4gICAgICBcbiAgICAgIDwhLS0gTm8gc2VhcmNoIHJlc3VsdHMgLS0+XG4gICAgICBAaWYgKHByb2plY3RzLmxlbmd0aCA+IDAgJiYgbWFzdGVyUHJvamVjdHMubGVuZ3RoID09PSAwICYmIHBoZFByb2plY3RzLmxlbmd0aCA9PT0gMCAmJiBhcmNoaXZlZFByb2plY3RzLmxlbmd0aCA9PT0gMCkge1xuICAgICAgICA8ZGl2IGNsYXNzPVwibm8tcmVzdWx0cyB0ZXh0LWNlbnRlciBweS04IHRleHQtc2Vjb25kYXJ5XCI+XG4gICAgICAgICAgTm8gcHJvamVjdHMgbWF0Y2hpbmcgXCJ7e3NlYXJjaFF1ZXJ5fX1cIlxuICAgICAgICA8L2Rpdj5cbiAgICAgIH1cbiAgICA8L2Rpdj5cbiAgfVxuPC9kaXY+XG5cbjwhLS0gUHJvamVjdCBDcmVhdGlvbiBEaWFsb2cgLS0+XG5AaWYgKHNob3dDcmVhdGVEaWFsb2cpIHtcbiAgPGRpdiBjbGFzcz1cIm1vZGFsLWJhY2tkcm9wIGFuaW1hdGUtZmFkZS1pblwiPlxuICAgIDxkaXYgY2xhc3M9XCJtb2RhbC1jb250YWluZXIgY2FyZCBnbGFzc1wiPlxuICAgICAgPGRpdiBjbGFzcz1cIm1vZGFsLWhlYWRlclwiPlxuICAgICAgICA8aDIgY2xhc3M9XCJ0ZXh0LXhsIGZvbnQtYm9sZFwiPk5ldyBQcm9qZWN0PC9oMj5cbiAgICAgICAgPGJ1dHRvbiBjbGFzcz1cImJ0biBidG4tZ2hvc3QgcC0xXCIgKGNsaWNrKT1cImNsb3NlQ3JlYXRlRGlhbG9nKClcIj5cbiAgICAgICAgICA8c3ZnIHhtbG5zPVwiaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmdcIiB3aWR0aD1cIjIwXCIgaGVpZ2h0PVwiMjBcIiB2aWV3Qm94PVwiMCAwIDI0IDI0XCIgZmlsbD1cIm5vbmVcIiBzdHJva2U9XCJjdXJyZW50Q29sb3JcIiBzdHJva2Utd2lkdGg9XCIyXCIgc3Ryb2tlLWxpbmVjYXA9XCJyb3VuZFwiIHN0cm9rZS1saW5lam9pbj1cInJvdW5kXCI+PGxpbmUgeDE9XCIxOFwiIHkxPVwiNlwiIHgyPVwiNlwiIHkyPVwiMThcIj48L2xpbmU+PGxpbmUgeDE9XCI2XCIgeTE9XCI2XCIgeDI9XCIxOFwiIHkyPVwiMThcIj48L2xpbmU+PC9zdmc+XG4gICAgICAgIDwvYnV0dG9uPlxuICAgICAgPC9kaXY+XG4gICAgICBcbiAgICAgIDxmb3JtIGNsYXNzPVwibW9kYWwtYm9keVwiIChuZ1N1Ym1pdCk9XCJjcmVhdGVQcm9qZWN0KClcIj5cbiAgICAgICAgPGRpdiBjbGFzcz1cImZvcm0tZ3JvdXBcIj5cbiAgICAgICAgICA8bGFiZWwgZm9yPVwicHJvamVjdE5hbWVcIj5Qcm9qZWN0IE5hbWUgPHNwYW4gY2xhc3M9XCJ0ZXh0LWVycm9yXCI+Kjwvc3Bhbj48L2xhYmVsPlxuICAgICAgICAgIDxpbnB1dCB0eXBlPVwidGV4dFwiIGlkPVwicHJvamVjdE5hbWVcIiBuYW1lPVwicHJvamVjdE5hbWVcIiBbKG5nTW9kZWwpXT1cIm5ld1Byb2plY3QubmFtZVwiIHJlcXVpcmVkIHBsYWNlaG9sZGVyPVwiZS5nLiwgTExNIFJlYXNvbmluZyBDYXBhYmlsaXRpZXNcIiBhdXRvZm9jdXM+XG4gICAgICAgIDwvZGl2PlxuICAgICAgICBcbiAgICAgICAgPGRpdiBjbGFzcz1cImZvcm0tZ3JvdXBcIj5cbiAgICAgICAgICA8bGFiZWwgZm9yPVwicHJvamVjdFRvcGljXCI+VG9waWM8L2xhYmVsPlxuICAgICAgICAgIDxpbnB1dCB0eXBlPVwidGV4dFwiIGlkPVwicHJvamVjdFRvcGljXCIgbmFtZT1cInByb2plY3RUb3BpY1wiIFsobmdNb2RlbCldPVwibmV3UHJvamVjdC50b3BpY1wiIHBsYWNlaG9sZGVyPVwiZS5nLiwgQXJ0aWZpY2lhbCBJbnRlbGxpZ2VuY2VcIj5cbiAgICAgICAgPC9kaXY+XG5cbiAgICAgICAgPGRpdiBjbGFzcz1cImZvcm0tZ3JvdXBcIj5cbiAgICAgICAgICA8bGFiZWwgZm9yPVwidGFyZ2V0TGV2ZWxcIj5UYXJnZXQgTGV2ZWw8L2xhYmVsPlxuICAgICAgICAgIDxzZWxlY3QgaWQ9XCJ0YXJnZXRMZXZlbFwiIG5hbWU9XCJ0YXJnZXRMZXZlbFwiIFsobmdNb2RlbCldPVwibmV3UHJvamVjdC50YXJnZXRfbGV2ZWxcIj5cbiAgICAgICAgICAgIDxvcHRpb24gdmFsdWU9XCJtYXN0ZXJcIj5NYXN0ZXIgTGV2ZWw8L29wdGlvbj5cbiAgICAgICAgICAgIDxvcHRpb24gdmFsdWU9XCJwaGRcIj5QaEQgTGV2ZWw8L29wdGlvbj5cbiAgICAgICAgICA8L3NlbGVjdD5cbiAgICAgICAgPC9kaXY+XG5cbiAgICAgICAgPGRpdiBjbGFzcz1cImZvcm0tZ3JvdXBcIj5cbiAgICAgICAgICA8bGFiZWwgZm9yPVwicHJvamVjdERlc2NcIj5EZXNjcmlwdGlvbjwvbGFiZWw+XG4gICAgICAgICAgPHRleHRhcmVhIGlkPVwicHJvamVjdERlc2NcIiBuYW1lPVwicHJvamVjdERlc2NcIiBbKG5nTW9kZWwpXT1cIm5ld1Byb2plY3QuZGVzY3JpcHRpb25cIiByb3dzPVwiM1wiIHBsYWNlaG9sZGVyPVwiQnJpZWYgZGVzY3JpcHRpb24gb2YgdGhlIHJlc2VhcmNoIGdvYWxzLi4uXCI+PC90ZXh0YXJlYT5cbiAgICAgICAgPC9kaXY+XG5cbiAgICAgICAgPGRpdiBjbGFzcz1cIm1vZGFsLWZvb3RlclwiPlxuICAgICAgICAgIDxidXR0b24gdHlwZT1cImJ1dHRvblwiIGNsYXNzPVwiYnRuIGJ0bi1naG9zdFwiIChjbGljayk9XCJjbG9zZUNyZWF0ZURpYWxvZygpXCI+Q2FuY2VsPC9idXR0b24+XG4gICAgICAgICAgPGJ1dHRvbiB0eXBlPVwic3VibWl0XCIgY2xhc3M9XCJidG4gYnRuLXByaW1hcnlcIiBbZGlzYWJsZWRdPVwiIW5ld1Byb2plY3QubmFtZS50cmltKCkgfHwgaXNDcmVhdGluZ1wiPlxuICAgICAgICAgICAge3sgaXNDcmVhdGluZyA/ICdDcmVhdGluZy4uLicgOiAnQ3JlYXRlIFByb2plY3QnIH19XG4gICAgICAgICAgPC9idXR0b24+XG4gICAgICAgIDwvZGl2PlxuICAgICAgPC9mb3JtPlxuICAgIDwvZGl2PlxuICA8L2Rpdj5cbn1cbiIsImltcG9ydCB7IFBpcGUsIFBpcGVUcmFuc2Zvcm0gfSBmcm9tICdAYW5ndWxhci9jb3JlJztcblxuQFBpcGUoe1xuICBuYW1lOiAncmVsYXRpdmVUaW1lJyxcbiAgc3RhbmRhbG9uZTogdHJ1ZVxufSlcbmV4cG9ydCBjbGFzcyBSZWxhdGl2ZVRpbWVQaXBlIGltcGxlbWVudHMgUGlwZVRyYW5zZm9ybSB7XG4gIHRyYW5zZm9ybSh2YWx1ZTogc3RyaW5nIHwgRGF0ZSB8IHVuZGVmaW5lZCB8IG51bGwpOiBzdHJpbmcge1xuICAgIGlmICghdmFsdWUpIHJldHVybiAnJztcbiAgICBjb25zdCBkYXRlID0gbmV3IERhdGUodmFsdWUpO1xuICAgIGlmIChpc05hTihkYXRlLmdldFRpbWUoKSkpIHJldHVybiAnJztcbiAgICBcbiAgICBjb25zdCBub3cgPSBuZXcgRGF0ZSgpO1xuICAgIGNvbnN0IGRpZmZNcyA9IG5vdy5nZXRUaW1lKCkgLSBkYXRlLmdldFRpbWUoKTtcbiAgICBcbiAgICBpZiAoZGlmZk1zIDwgMCkgcmV0dXJuICdpbiB0aGUgZnV0dXJlJztcbiAgICBcbiAgICBjb25zdCBkaWZmTWlucyA9IE1hdGguZmxvb3IoZGlmZk1zIC8gNjAwMDApO1xuICAgIGNvbnN0IGRpZmZIb3VycyA9IE1hdGguZmxvb3IoZGlmZk1pbnMgLyA2MCk7XG4gICAgY29uc3QgZGlmZkRheXMgPSBNYXRoLmZsb29yKGRpZmZIb3VycyAvIDI0KTtcblxuICAgIGlmIChkaWZmTWlucyA8IDEpIHJldHVybiAnbm93JztcbiAgICBpZiAoZGlmZk1pbnMgPCA2MCkgcmV0dXJuIGAke2RpZmZNaW5zfW1gO1xuICAgIGlmIChkaWZmSG91cnMgPCAyNCkgcmV0dXJuIGAke2RpZmZIb3Vyc31oYDtcbiAgICByZXR1cm4gYCR7ZGlmZkRheXN9ZGA7XG4gIH1cbn1cbiJdLCJtYXBwaW5ncyI6Ijs7Ozs7Ozs7OztBQUFBLFNBQVMsaUJBQXlCO0FBQ2xDLFNBQVMsb0JBQW9CO0FBQzdCLFNBQWlCLG9CQUFvQjtBQUNyQyxTQUFTLG1CQUFtQjs7O0FFSDVCLFNBQVMsWUFBMkI7O0FBTTlCLElBQU8sbUJBQVAsTUFBTyxrQkFBZ0I7RUFDM0IsVUFBVSxPQUF1QztBQUMvQyxRQUFJLENBQUM7QUFBTyxhQUFPO0FBQ25CLFVBQU0sT0FBTyxJQUFJLEtBQUssS0FBSztBQUMzQixRQUFJLE1BQU0sS0FBSyxRQUFPLENBQUU7QUFBRyxhQUFPO0FBRWxDLFVBQU0s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QUFBLGVBQUEsR0FBQSxPQUFBLEdBQUEsQ0FBQSxTQUFBLDhCQUFBLFNBQUEsTUFBQSxVQUFBLE1BQUEsV0FBQSxhQUFBLFFBQUEsUUFBQSxVQUFBLGdCQUFBLGdCQUFBLEtBQUEsa0JBQUEsU0FBQSxtQkFBQSxPQUFBLEdBQUEsQ0FBQSxNQUFBLE1BQUEsTUFBQSxLQUFBLE1BQUEsTUFBQSxNQUFBLElBQUEsR0FBQSxDQUFBLE1BQUEsS0FBQSxNQUFBLE1BQUEsTUFBQSxNQUFBLE1BQUEsSUFBQSxHQUFBLENBQUEsR0FBQSxZQUFBLEdBQUEsQ0FBQSxTQUFBLDhCQUFBLFNBQUEsTUFBQSxVQUFBLE1BQUEsV0FBQSxhQUFBLFFBQUEsUUFBQSxVQUFBLGdCQUFBLGdCQUFBLEtBQUEsa0JBQUEsU0FBQSxtQkFBQSxTQUFBLEdBQUEsYUFBQSxHQUFBLENBQUEsTUFBQSxNQUFBLE1BQUEsTUFBQSxLQUFBLEdBQUEsR0FBQSxDQUFBLE1BQUEsTUFBQSxNQUFBLE1BQUEsTUFBQSxTQUFBLE1BQUEsT0FBQSxHQUFBLENBQUEsUUFBQSxRQUFBLGVBQUEscURBQUEsR0FBQSxpQkFBQSxTQUFBLFNBQUEsR0FBQSxDQUFBLFdBQUEsbUJBQUEsZUFBQSxnRkFBQSxXQUFBLDZCQUFBLEdBQUEsV0FBQSxHQUFBLENBQUEsR0FBQSxlQUFBLEdBQUEsQ0FBQSxHQUFBLG9CQUFBLEdBQUEsQ0FBQSxHQUFBLGtCQUFBLGlCQUFBLEdBQUEsQ0FBQSxTQUFBLDBCQUFBLEdBQUEsU0FBQSxTQUFBLEdBQUEsQ0FBQSxHQUFBLGlCQUFBLFVBQUEsR0FBQSxDQUFBLEdBQUEsZUFBQSxHQUFBLENBQUEsR0FBQSxpQkFBQSxVQUFBLEdBQUEsQ0FBQSxHQUFBLGNBQUEsZUFBQSxRQUFBLGdCQUFBLEdBQUEsQ0FBQSxHQUFBLGVBQUEsZ0JBQUEsR0FBQSxDQUFBLEdBQUEsU0FBQSxZQUFBLEdBQUEsQ0FBQSxHQUFBLGNBQUEsR0FBQSxDQUFBLEdBQUEsZ0JBQUEsUUFBQSxTQUFBLEdBQUEsWUFBQSxHQUFBLENBQUEsR0FBQSxhQUFBLEdBQUEsQ0FBQSxHQUFBLGNBQUEsR0FBQSxDQUFBLEdBQUEsZ0JBQUEsV0FBQSxZQUFBLEdBQUEsQ0FBQSxHQUFBLGlCQUFBLFdBQUEsYUFBQSxHQUFBLENBQUEsR0FBQSxnQkFBQSxXQUFBLGtCQUFBLFVBQUEsR0FBQSxDQUFBLEdBQUEsYUFBQSxHQUFBLENBQUEsR0FBQSxTQUFBLGVBQUEsR0FBQSxDQUFBLEdBQUEsU0FBQSxlQUFBLEdBQUEsQ0FBQSxHQUFBLE9BQUEsR0FBQSxDQUFBLEdBQUEsZ0JBQUEsUUFBQSxTQUFBLGNBQUEsR0FBQSxZQUFBLEdBQUEsQ0FBQSxHQUFBLGdCQUFBLFlBQUEsR0FBQSxDQUFBLEdBQUEsZUFBQSxNQUFBLEdBQUEsQ0FBQSxHQUFBLG1CQUFBLFFBQUEsT0FBQSxHQUFBLENBQUEsR0FBQSxjQUFBLEdBQUEsQ0FBQSxHQUFBLFdBQUEsV0FBQSxHQUFBLENBQUEsR0FBQSxPQUFBLGFBQUEsT0FBQSxHQUFBLE9BQUEsR0FBQSxDQUFBLFNBQUEsOEJBQUEsU0FBQSxNQUFBLFVBQUEsTUFBQSxXQUFBLGFBQUEsUUFBQSxRQUFBLFVBQUEsZ0JBQUEsZ0JBQUEsS0FBQSxrQkFBQSxTQUFBLG1CQUFBLE9BQUEsR0FBQSxDQUFBLE1BQUEsTUFBQSxNQUFBLEtBQUEsTUFBQSxLQUFBLE1BQUEsSUFBQSxHQUFBLENBQUEsTUFBQSxLQUFBLE1BQUEsS0FBQSxNQUFBLE1BQUEsTUFBQSxJQUFBLEdBQUEsQ0FBQSxHQUFBLGNBQUEsR0FBQSxVQUFBLEdBQUEsQ0FBQSxHQUFBLFlBQUEsR0FBQSxDQUFBLE9BQUEsYUFBQSxHQUFBLENBQUEsR0FBQSxZQUFBLEdBQUEsQ0FBQSxRQUFBLFFBQUEsTUFBQSxlQUFBLFFBQUEsZUFBQSxZQUFBLElBQUEsZUFBQSxvQ0FBQSxhQUFBLElBQUEsR0FBQSxpQkFBQSxTQUFBLEdBQUEsQ0FBQSxPQUFBLGNBQUEsR0FBQSxDQUFBLFFBQUEsUUFBQSxNQUFBLGdCQUFBLFFBQUEsZ0JBQUEsZUFBQSxpQ0FBQSxHQUFBLGlCQUFBLFNBQUEsR0FBQSxDQUFBLE9BQUEsYUFBQSxHQUFBLENBQUEsTUFBQSxlQUFBLFFBQUEsZUFBQSxHQUFBLGlCQUFBLFNBQUEsR0FBQSxDQUFBLFNBQUEsUUFBQSxHQUFBLENBQUEsU0FBQSxLQUFBLEdBQUEsQ0FBQSxPQUFBLGFBQUEsR0FBQSxDQUFBLE1BQUEsZUFBQSxRQUFBLGVBQUEsUUFBQSxLQUFBLGVBQUEsOENBQUEsR0FBQSxpQkFBQSxTQUFBLEdBQUEsQ0FBQSxHQUFBLGNBQUEsR0FBQSxDQUFBLFFBQUEsVUFBQSxHQUFBLE9BQUEsYUFBQSxHQUFBLE9BQUEsR0FBQSxDQUFBLFFBQUEsVUFBQSxHQUFBLE9BQUEsZUFBQSxHQUFBLFVBQUEsQ0FBQSxHQUFBLFVBQUEsU0FBQSx5QkFBQSxJQUFBLEtBQUE7QUFBQSxRQUFBLEtBQUEsR0FBQTtBQ2Y1QixNQUFBLDZCQUFBLEdBQUEsT0FBQSxDQUFBLEVBQWlELEdBQUEsVUFBQSxDQUFBLEVBRW5CLEdBQUEsT0FBQSxDQUFBLEVBQ0UsR0FBQSxPQUFBLENBQUEsRUFDQyxHQUFBLE1BQUEsQ0FBQTtBQUNtQixNQUFBLHFCQUFBLEdBQUEsbUJBQUE7QUFBaUIsTUFBQSwyQkFBQTtBQUM3RCxNQUFBLDZCQUFBLEdBQUEsS0FBQSxDQUFBO0FBQStCLE1BQUEscUJBQUEsR0FBQSw2Q0FBQTtBQUEyQyxNQUFBLDJCQUFBLEVBQUk7QUFFaEYsTUFBQSw2QkFBQSxHQUFBLE9BQUEsQ0FBQSxFQUE0QixHQUFBLFNBQUEsQ0FBQSxFQUNHLElBQUEsU0FBQSxDQUFBO0FBQ3FCLE1BQUEseUJBQUEsVUFBQSxTQUFBLG9EQUFBO0FBQUEsZUFBVSxJQUFBLGVBQUE7TUFBZ0IsQ0FBQTtBQUExRSxNQUFBLDJCQUFBO0FBQ0EsTUFBQSx3QkFBQSxJQUFBLFFBQUEsQ0FBQTtBQUNBLE1BQUEsNkJBQUEsSUFBQSxRQUFBLEVBQUE7QUFBZ0QsTUFBQSxxQkFBQSxJQUFBLGVBQUE7QUFBYSxNQUFBLDJCQUFBLEVBQU87QUFFdEUsTUFBQSw2QkFBQSxJQUFBLFVBQUEsRUFBQTtBQUFnQyxNQUFBLHlCQUFBLFNBQUEsU0FBQSxvREFBQTtBQUFBLGVBQVMsSUFBQSxpQkFBQTtNQUFrQixDQUFBOztBQUN6RCxNQUFBLDZCQUFBLElBQUEsT0FBQSxFQUFBO0FBQXFMLE1BQUEsd0JBQUEsSUFBQSxRQUFBLEVBQUEsRUFBNEMsSUFBQSxRQUFBLEVBQUE7QUFBNEMsTUFBQSwyQkFBQTtBQUM3USxNQUFBLHFCQUFBLElBQUEsZUFBQTtBQUNGLE1BQUEsMkJBQUEsRUFBUyxFQUNMOztBQUlSLE1BQUEsNkJBQUEsSUFBQSxPQUFBLEVBQUE7O0FBQ0UsTUFBQSw2QkFBQSxJQUFBLE9BQUEsRUFBQTtBQUF5TSxNQUFBLHdCQUFBLElBQUEsVUFBQSxFQUFBLEVBQXVDLElBQUEsUUFBQSxFQUFBO0FBQW1ELE1BQUEsMkJBQUE7O0FBQ25TLE1BQUEsNkJBQUEsSUFBQSxTQUFBLEVBQUE7QUFBbUYsTUFBQSwrQkFBQSxpQkFBQSxTQUFBLHlEQUFBLFFBQUE7QUFBQSxRQUFBLGlDQUFBLElBQUEsYUFBQSxNQUFBLE1BQUEsSUFBQSxjQUFBO0FBQUEsZUFBQTtNQUFBLENBQUE7QUFBMEIsTUFBQSx5QkFBQSxTQUFBLFNBQUEsbURBQUE7QUFBQSxlQUFTLElBQUEsZUFBQTtNQUFnQixDQUFBO0FBQXRJLE1BQUEsMkJBQUEsRUFBd0ksRUFDcEk7QUFJUixNQUFBLGtDQUFBLElBQUEseUNBQUEsR0FBQSxHQUFBLG1CQUFBLEVBQUE7QUFVQSxNQUFBLGtDQUFBLElBQUEseUNBQUEsR0FBQSxHQUFBLE9BQUEsRUFBQTtBQU9BLE1BQUEsa0NBQUEsSUFBQSx5Q0FBQSxHQUFBLEdBQUEsT0FBQSxFQUFBO0FBcUZGLE1BQUEsMkJBQUE7QUFHQSxNQUFBLGtDQUFBLElBQUEseUNBQUEsSUFBQSxHQUFBLE9BQUEsRUFBQTs7O0FBNUhpQyxNQUFBLHdCQUFBLEVBQUE7QUFBQSxNQUFBLHlCQUFBLFdBQUEsSUFBQSxZQUFBO0FBY3dELE1BQUEsd0JBQUEsRUFBQTtBQUFBLE1BQUEsK0JBQUEsV0FBQSxJQUFBLFdBQUE7QUFLdkYsTUFBQSx3QkFBQTtBQUFBLE1BQUEsNEJBQUEsQ0FBQSxJQUFBLGFBQUEsSUFBQSxTQUFBLFdBQUEsSUFBQSxLQUFBLEVBQUE7QUFVQSxNQUFBLHdCQUFBO0FBQUEsTUFBQSw0QkFBQSxJQUFBLFlBQUEsS0FBQSxFQUFBO0FBT0EsTUFBQSx3QkFBQTtBQUFBLE1BQUEsNEJBQUEsQ0FBQSxJQUFBLGFBQUEsSUFBQSxTQUFBLFNBQUEsSUFBQSxLQUFBLEVBQUE7QUF3RkYsTUFBQSx3QkFBQTtBQUFBLE1BQUEsNEJBQUEsSUFBQSxtQkFBQSxLQUFBLEVBQUE7O29CRDNIWSxjQUFZLFlBQUEsc0JBQUEsWUFBQSxTQUFBLHFCQUFBLFlBQUEsYUFBQSxpQkFBQSxvQkFBQSxhQUFBLGlCQUFFLGNBQVksaUJBQUEsZUFBQSxxQkFBQSwrQkFBRSxhQUFXLHVCQUFBLG1CQUFBLGlDQUFBLHlCQUFBLHdCQUFBLHVCQUFBLGlDQUFBLCtCQUFBLHVDQUFBLDhCQUFBLG9CQUFBLHlCQUFBLHNCQUFBLHVCQUFBLHVCQUFBLHFCQUFBLDhCQUFBLG1CQUFBLGlCQUFBLGlCQUFBLFlBQUEsaUJBQUEsV0FBb0IscUJBQW1CLGNBQUEsa0JBQUEsa0JBQUEsYUFBQSxjQUFBLGdCQUFBLGdCQUFBLGtCQUFBLGlCQUFBLGFBQUEsbUJBQUEsbUJBQUEsaUJBQXJDLGdCQUFnQixHQUFBLFFBQUEsQ0FBQSx1OEtBQUEsRUFBQSxDQUFBOzs7Z0ZBSXhELGlCQUFlLENBQUE7VUFQM0I7dUJBQ1csb0JBQWtCLFlBQ2hCLE1BQUksU0FDUCxDQUFDLGNBQWMsY0FBYyxhQUFhLGtCQUFrQixtQkFBbUIsR0FBQyxVQUFBOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7O0dBQUEsUUFBQSxDQUFBLG05SUFBQSxFQUFBLENBQUE7Ozs7aUZBSTlFLGlCQUFlLEVBQUEsV0FBQSxtQkFBQSxVQUFBLCtEQUFBLFlBQUEsR0FBQSxDQUFBO0FBQUEsR0FBQTs7Ozs7OzsrREFBZixpQkFBZSxFQUFBLFNBQUEsQ0FBQUEsS0FBQSxJQUFBLElBQUEsSUFBQSxtQkFBQSxHQUFBLENBQUEsY0FBQSxjQUFBLGFBQUEscUJBQUEsa0JBQUEsU0FBQSxHQUFBLGFBQUEsRUFBQSxDQUFBO0VBQUE7QUFBQSxHQUFBLE9BQUEsY0FBQSxlQUFBLGNBQUEsd0JBQUEsS0FBQSxJQUFBLENBQUE7QUFBQSxHQUFBLE9BQUEsY0FBQSxlQUFBLGVBQUEsWUFBQSxPQUFBLFlBQUEsSUFBQSxHQUFBLDRCQUFBLE9BQUEsRUFBQSxPQUFBLE1BQUEsd0JBQUEsRUFBQSxTQUFBLENBQUE7QUFBQSxHQUFBOyIsIm5hbWVzIjpbImkwIl19