angular.module('checkmate.DeploymentData')
  .directive('deploymentEditor', function(DeploymentData, $timeout, Blueprint) {
    return {
      restrict: 'E',
      replace: true,
      scope: {},
      template: '<div class="deployment-editor">\
                  <checkmate-codemirror checkmate-codemirror-opts="codemirror.options" ng-model="deployment" ui-refresh="codemirror.options.mode"></checkmate-codemirror>\
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
        $scope.deployment = '';

        var _to_yaml = function() {
          $scope.deployment = jsyaml.safeDump(JSON.parse($scope.deployment));
          $scope.codemirror.options.mode = 'text/x-yaml';
          $scope.codemirror.foldFunction = CodeMirror.newFoldFunction(CodeMirror.fold.indent);
        };

        var _to_json = function() {
          $scope.deployment = JSON.stringify(jsyaml.safeLoad($scope.deployment), undefined, 2);
          $scope.codemirror.options.mode = 'application/json';
          $scope.codemirror.foldFunction = CodeMirror.newFoldFunction(CodeMirror.fold.brace);
        };

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
                _to_yaml();
              } else {
                _to_json();
              }
            } catch(e) {
              console.error(e);
            }
          },
          foldFunction: CodeMirror.newFoldFunction(CodeMirror.fold.indent),
          foldDefault: function(editor) {
            // var inBlueprint = false;
            // editor.eachLine(function(line) {
            //   if (line.text.substring(0, 1) !== ' ') {
            //     if (line.text.substring(0, 10) == 'blueprint:') {
            //       inBlueprint = true;
            //    } else {
            //       inBlueprint = false;
            //       $scope.codemirror.foldFunction(editor, editor.getLineNumber(line));
            //     }
            //   } else if (inBlueprint && line.text.substring(0, 10) === '  options:') {
            //     $scope.codemirror.foldFunction(editor, editor.getLineNumber(line));
            //   } else if (inBlueprint && line.text.substring(0, 12) === '  meta-data:') {
            //     $scope.codemirror.foldFunction(editor, editor.getLineNumber(line));
            //   }
            // });
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
            $scope.codemirror.markAltered();
            return $scope.codemirror.foldFunction(editor, start);
          },
          onLoad: function(_editor) {
            _editor.on("change", function(d) {
              try {
                var deployment = jsyaml.load($scope.deployment);
                $scope.$emit('editor:nsync');
                DeploymentData.set(deployment);
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
              newDeployment = JSON.stringify(data, undefined, 2);
            } else {
              newDeployment = jsyaml.safeDump(data);
            }

            if ($scope.deployment != newDeployment) {
              $timeout(function() {
                $scope.deployment = newDeployment;
              });
            }
          }
        });

      }
    };
  });
