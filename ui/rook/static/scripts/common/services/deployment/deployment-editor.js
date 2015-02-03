angular.module('checkmate.DeploymentData')
  .directive('deploymentEditor', function(DeploymentData, $timeout, Blueprint) {
    return {
      restrict: 'E',
      replace: true,
      scope: {},
      template: '<div class="deployment-editor">\
                  <checkmate-codemirror checkmate-codemirror-opts="codemirror.options" ng-model="codeText" ui-refresh="codemirror.options.mode"></checkmate-codemirror>\
                  <div class="toggle-editor btn-group">\
                    <button class="btn btn-mini" \
                            ng-click="codemirror.toggleMode()"\
                            ng-disabled="codemirror.options.mode == \'text/x-yaml\'"\
                            disabled="disabled">\
                      YAML\
                    </button>\
                    <button class="btn btn-mini"\
                            ng-click="codemirror.toggleMode()"\
                            ng-disabled="codemirror.options.mode == \'application/json\'">\
                    JSON\
                    </button>\
                  </div>\
                </div>',
      controller: function($scope) {
        var getLineLabel = function(line) {
          return line.text.replace(/[^a-zA-Z0-9_-]+/g, "");
        };

        $scope.codeText = '';

        $scope.codemirror = {
          editor: null,
          editorAltered: false,
          isFocused: false,
          markAltered: function() {
            $scope.codemirror.editorAltered = true;
          },
          toggleMode: function() {
            try {
              if ($scope.codemirror.options.mode == 'application/json') {
                $scope.codeText = jsyaml.safeDump(JSON.parse($scope.codeText));
                $scope.codemirror.options.mode = 'text/x-yaml';
                $scope.codemirror.foldFunction = CodeMirror.newFoldFunction(CodeMirror.fold.indent);
              } else {
                $scope.codeText = JSON.stringify(jsyaml.safeLoad($scope.codeText), undefined, 2);
                $scope.codemirror.options.mode = 'application/json';
                $scope.codemirror.foldFunction = CodeMirror.newFoldFunction(CodeMirror.fold.brace);
              }
            } catch(e) {
              console.error(e);
            }
          },
          trackedFolds: [
             'blueprint', 'environment', 'inputs', 'meta-data', 'options', 'services'
          ],
          folds: {
            'meta-data': { folded: true },
            'options': { folded: true },
            'environment': { folded: true }
          },
          foldFunction: CodeMirror.newFoldFunction(CodeMirror.fold.indent),
          foldDefault: function(editor) {
            var that = this;

            editor.eachLine(function(line) {
              var prop = getLineLabel(line);

              if(that.folds[prop] && that.folds[prop].folded) {
                $scope.codemirror.foldFunction(editor, editor.getLineNumber(line));
              }
            });
          },
          setEditorDefaultState: function(editor) {
            $scope.codemirror.foldDefault(editor);
          }
        };

        $scope.codemirror.options = {
          lint: true,
          mode: 'text/x-yaml',
          theme: 'lesser-dark',
          lineNumbers: true,
          autoFocus: true,
          lineWrapping: true,
          dragDrop: false,
          matchBrackets: true,
          foldGutter: true,
          extraKeys: {"Ctrl-Q": function(cm){ cm.foldCode(cm.getCursor()); }},
          gutters: ['CodeMirror-lint-markers','CodeMirror-linenumbers', 'CodeMirror-foldgutter'],
          onGutterClick: function(editor, start) {
            var line = editor.lineInfo(start);
            var prop = getLineLabel(line);
            var fold;

            if(prop && $scope.codemirror.trackedFolds.indexOf(prop) > -1) {
              fold = $scope.codemirror.folds[prop];

              if(!fold) {
                $scope.codemirror.folds[prop] = {
                  folded: false
                };

                fold = $scope.codemirror.folds[prop]
              }

              fold.folded = !fold.folded;
            }

            $scope.codemirror.markAltered();
            return $scope.codemirror.foldFunction(editor, start);
          },
          onLoad: function(_editor) {
            _editor.on("change", function(d) {
              try {
                var deployment = jsyaml.load($scope.codeText);
                $scope.$emit('editor:nsync');
                Blueprint.set(deployment);
              } catch(e) {
                $scope.$emit('editor:out_of_sync');
                $scope.$apply();
              }
            });
          },
          onFocus: function() {
            $scope.codemirror.markAltered();
            $scope.codemirror.isFocused = true;
            $scope.$emit('editor:focus');
          },
          onBlur: function() {
            $scope.codemirror.isFocused = false;
            $scope.$emit('editor:blur');
          }
        };

        $scope.$on('editor:refreshed', function(event, editor, viewData) {
          $scope.codemirror.setEditorDefaultState(editor);
        });

        $scope.$on('deployment:update', function(event, data) {
          if(!$scope.codemirror.isFocused) {
            var newDeployment;

            if($scope.codemirror.options.mode == 'application/json') {
              newDeployment = JSON.stringify(data.blueprint, undefined, 2);
            } else {
              newDeployment = jsyaml.safeDump(data.blueprint);
            }

            if ($scope.codeText != newDeployment) {
              $timeout(function() {
                $scope.codeText = newDeployment;
              });
            }
          }
        });

      }
    };
  });
