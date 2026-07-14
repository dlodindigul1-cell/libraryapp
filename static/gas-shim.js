/**
 * gas-shim.js
 * -----------------------------------------------------------
 * Google Apps Script-ன் "google.script.run" object-ஐ browser-ல்
 * அப்படியே fake செய்யும் shim. இதனால் பழைய GAS frontend code
 * (google.script.run.withSuccessHandler(fn).functionName(args))
 * எந்த மாற்றமும் இல்லாமல் Flask backend-உடன் வேலை செய்யும்.
 *
 * ஒவ்வொரு .functionName(args) call-உம் இப்படி மாறும்:
 *   POST  /leave/api/functionName   body: { args: [args] }
 * -----------------------------------------------------------
 */
(function () {
  "use strict";

  // இந்த base path-ஐ ஒவ்வொரு app-க்கும் தனித்தனியா HTML-ல் மாற்றலாம்.
  // Default: இதே பக்கம் இருக்கும் இடத்தை base ஆக எடுத்துக்கும்.
  var API_BASE = window.GAS_API_BASE || (window.location.pathname.replace(/\/$/, "") + "/api/");

  function createRunner(successHandler, failureHandler) {
    return new Proxy(function () {}, {
      get: function (target, prop) {
        if (prop === "withSuccessHandler") {
          return function (fn) { return createRunner(fn, failureHandler); };
        }
        if (prop === "withFailureHandler") {
          return function (fn) { return createRunner(successHandler, fn); };
        }
        if (prop === "withUserObject") {
          // GAS-ல் withUserObject callback-க்கு கூடுதல் context கொடுக்கும்.
          // இங்கே simple ஆக அதே runner-ஐ திருப்பி அனுப்புகிறோம்.
          return function () { return createRunner(successHandler, failureHandler); };
        }
        // இதுவே server-side function பெயர் (எ.கா getAllEmployees)
        return function () {
          var args = Array.prototype.slice.call(arguments);
          fetch(API_BASE + prop, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ args: args })
          })
            .then(function (r) {
              if (!r.ok) {
                return r.json().catch(function () {
                  throw new Error("Server error: HTTP " + r.status);
                }).then(function (j) {
                  throw new Error((j && j.__gasError__) || ("Server error: HTTP " + r.status));
                });
              }
              return r.json();
            })
            .then(function (data) {
              if (data && typeof data === "object" && "__gasError__" in data) {
                if (failureHandler) failureHandler({ message: data.__gasError__ });
              } else {
                if (successHandler) successHandler(data);
              }
            })
            .catch(function (err) {
              if (failureHandler) failureHandler(err);
              else console.error("google.script.run error (" + prop + "):", err);
            });
        };
      }
    });
  }

  window.google = window.google || {};
  window.google.script = window.google.script || {};
  window.google.script.run = createRunner(null, null);
})();
