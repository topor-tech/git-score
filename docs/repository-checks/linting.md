# lct-git-score: линтинг и линтеры в проекте

Статус: предлагаемое расширение методологии, версия 0.2. Дата: 2026-09-09.

Связанные документы: [общий подход](approach.md), [полный каталог проверок](checks.md).

## 1. Что оценивается

Блок LT01–LT16 проверяет, что подходящие инструменты выбраны, их правила воспроизводимы, нужный код действительно анализируется, а результат влияет на возможность merge. Наличие файла `.pre-commit-config.yaml` или job с названием `lint` — только начальные признаки настройки.

«Топ инструментов» ниже означает практический shortlist для распространённых языков и стеков. Это экспертная рекомендация для выбора, а не статистический рейтинг долей рынка. Первый инструмент в строке — рекомендуемая отправная точка; альтернативы нужны при других требованиях или уже сложившемся процессе. Проверка здоровья не требует переходить на первый инструмент, если существующий решает задачу.

Версии и возможности следует проверять для конкретного установленного релиза. Ссылки ведут на официальную документацию или репозитории разработчиков. Новые правила, команды и форматы конфигурации могут отличаться между major-версиями.

## 2. Линтер, форматтер и статический анализатор

| Класс | Назначение | Примеры | Что не следует подменять |
| --- | --- | --- | --- |
| Линтер | Типичные ошибки, подозрительные конструкции, соглашения и часть правил стиля | Ruff check, ESLint, RuboCop, ShellCheck | Форматированием нельзя подтвердить отсутствие ошибок |
| Форматтер | Единое представление кода: пробелы, переносы, скобки | Ruff format, Prettier, rustfmt, clang-format | Наличие форматтера не закрывает весь Q06/LT-блок |
| Статический/типовой анализатор | Типы, потоки данных, более глубокие дефекты | mypy, PHPStan, SpotBugs, Roslyn analyzers | Нельзя автоматически считать его SAST или заменой тестов |
| Запускатель | Выбор файлов, установка окружения и вызов инструментов | pre-commit, Husky + lint-staged, Lefthook, CI jobs | Сам запускатель не содержит обязательного набора lint-правил |

Границы пересекаются: Clippy, detekt, clang-tidy и Roslyn сочетают lint и статический анализ, Ruff/Biome/RuboCop умеют несколько режимов. Для оценки фиксируется реально запущенный режим и набор правил, а не только название продукта.

## 3. Инструменты для распространённых языков

Команды — примеры проверки без исправления исходников. Они предполагают, что инструмент, нужные plugins, зависимости и build tasks уже установлены и настроены. Пути вроде `src/main.cpp` и `scripts/ci.sh` иллюстративны; в реальном репозитории команда обязана покрывать весь объявленный scope. Нельзя засчитывать анализ одного примера как проверку всего проекта.

| Язык / стек | Основной выбор и альтернативы | Что искать в репозитории | Пример запуска / существенная оговорка |
| --- | --- | --- | --- |
| Python | **[Ruff](https://docs.astral.sh/ruff/configuration/)**; [Pylint](https://pylint.readthedocs.io/en/latest/user_guide/usage/run.html) для дополнительных проверок; [Flake8](https://flake8.pycqa.org/en/latest/user/configuration.html) для существующего plugin-based процесса | Ruff: `[tool.ruff]` в `pyproject.toml`, `ruff.toml`, `.ruff.toml`; Pylint: `.pylintrc`, `pylintrc`, tool sections; Flake8: `.flake8`, `[flake8]` в `setup.cfg`/`tox.ini` | `ruff check .`; отдельно `ruff format --check .`. Сам `pyproject.toml` не доказывает настройку Ruff. Flake8 не получает TOML-конфиг автоматически без соответствующей интеграции |
| JavaScript / TypeScript | **[ESLint](https://eslint.org/docs/latest/use/configure/configuration-files)**; для TS — [typescript-eslint](https://typescript-eslint.io/getting-started/); **[Biome](https://biomejs.dev/guides/configure-biome/)** как альтернатива для подходящего набора правил и файлов | `eslint.config.js/mjs/cjs/ts/mts/cts`; legacy `.eslintrc.*` с учётом версии; Biome: `biome.json`, `biome.jsonc`; `package.json` и lockfile | Локально установленный `eslint . --max-warnings 0`; либо `biome lint .` с настроенным порогом severity. TS-конфиг может требовать дополнительной поддержки runtime. Typed lint требует отдельной настройки; `tsconfig.json` сам по себе не lint-конфиг |
| Java | **[Checkstyle](https://checkstyle.org/config.html)** для соглашений; [PMD](https://docs.pmd-code.org/latest/pmd_userdocs_making_rulesets.html) для исходников; [SpotBugs](https://spotbugs.github.io/) для bytecode analysis | Checkstyle XML, PMD ruleset XML, SpotBugs filters; реальные пути берутся из `pom.xml`, `build.gradle`/`build.gradle.kts` и plugins | `./mvnw checkstyle:check` или настроенные Gradle check tasks. Объявленный Maven plugin без привязки/вызова goal не доказывает запуск |
| C# / .NET | **[Roslyn/.NET analyzers](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/configuration-files)**; дополнительные style analyzers по политике | `.editorconfig`, `.globalconfig`, `.csproj`, `Directory.Build.props/targets`; analysis levels, analyzer packages, severities; SDK в `global.json` | `dotnet build --no-incremental -warnaserror` при включённом анализе; `dotnet format --verify-no-changes` отдельно. Проверить, какие diagnostics включены при build |
| C / C++ | **[clang-tidy](https://clang.llvm.org/extra/clang-tidy/)**; [Cppcheck](https://github.com/cppcheck-opensource/cppcheck) как дополнительный анализ | `.clang-tidy`, CMake/build settings, `compile_commands.json`; Cppcheck project/suppressions; `.clang-format` относится к форматированию | `clang-tidy -p build src/main.cpp --warnings-as-errors='*'`; для проекта — runner по translation units. Compilation database/flags должны соответствовать реальной сборке |
| Go | **[golangci-lint](https://golangci-lint.run/docs/configuration/)** как агрегатор; [Staticcheck](https://staticcheck.dev/docs/) как отдельный анализ; `go vet` как базовое дополнение | `.golangci.yml/yaml/toml/json`; schema/version; `staticcheck.conf`; `go.mod`, toolchain и закрепление tools | `golangci-lint run ./...`; отдельно `staticcheck ./...`, если он не покрыт агрегатором. Учитывать build tags, OS/arch и активные модули |
| Rust | **[Clippy](https://github.com/rust-lang/rust-clippy)**; rustfmt отдельно | `clippy.toml`, `.clippy.toml`, `[lints]`/`[workspace.lints]` в `Cargo.toml`, code attributes; `rust-toolchain.toml`; `rustfmt.toml` для formatter | `cargo clippy --workspace --all-targets -- -D warnings`; `cargo fmt --all -- --check`. Clippy может работать без отдельного config; features matrix задаётся проектом |
| PHP | **[PHP_CodeSniffer](https://github.com/PHPCSStandards/PHP_CodeSniffer)** для coding standard; [PHPStan](https://phpstan.org/config-reference) как дополнительный статический анализ | `phpcs.xml`, `.phpcs.xml`, варианты `.dist`; `phpstan.neon`, `phpstan.neon.dist`; `composer.json/lock`; выбранный standard и paths | `vendor/bin/phpcs`; отдельно `vendor/bin/phpstan analyse`. `php -l` проверяет синтаксис, но не заменяет эти контроли |
| Ruby | **[RuboCop](https://github.com/rubocop/rubocop)**; дополнительные cops для Rails/RSpec по стеку | `.rubocop.yml`, inherited/shared configs, `.rubocop_todo.yml`, `Gemfile/lock` | `bundle exec rubocop`. TODO/baseline может скрывать старые нарушения — отслеживать его отдельно |
| Kotlin / Android | **[detekt](https://detekt.dev/docs/introduction/configurations/)** для анализа; **[ktlint](https://github.com/ktlint/ktlint)** для соглашений/стиля | `detekt.yml/yaml` по пути из Gradle; `.editorconfig` для ktlint; `build.gradle.kts`, plugins и baseline | `./gradlew detekt`; при подключённом соответствующем plugin — `./gradlew ktlintCheck`. Имя/набор tasks зависит от интеграции |
| Swift | **[SwiftLint](https://github.com/realm/SwiftLint)** | `.swiftlint.yml`, nested configs, include/exclude rules; SwiftPM/build plugin либо CI command | `swiftlint lint --strict`. Учитывать target/source scope, custom rules и версии Swift/toolchain |
| Dart / Flutter | **[Dart analyzer + linter rules](https://dart.dev/tools/analysis)**; presets `lints` или `flutter_lints` | `analysis_options.yaml`, `include`, `linter.rules`, `analyzer.exclude`; `pubspec.yaml/lock` | `dart analyze --fatal-infos` или `flutter analyze`; formatter запускается отдельно. Severity и выбранный preset входят в evidence |
| Scala | **[Scalafix](https://scalacenter.github.io/scalafix/docs/users/configuration.html)** для configured lint/rewrite rules; compiler warnings дополняют анализ | `.scalafix.conf`, `build.sbt`, `project/plugins.sbt`, SemanticDB для semantic rules; `.scalafmt.conf` только для formatter | `sbt 'scalafixAll --check'` при подключённом plugin; проверить включённые правила и diagnostic severities |
| R | **[lintr](https://lintr.r-lib.org/articles/lintr.html)** | `.lintr`, исключения, `DESCRIPTION` и зафиксированные зависимости; учитывать project/package scope | `lintr::lint_dir()` или `lintr::lint_package()` внутри R runner, который завершает процесс ненулевым кодом при запрещённых findings. Простой вывод списка не гарантирует CI failure |
| Bash / POSIX shell | **[ShellCheck](https://github.com/koalaman/shellcheck)**; форматирование отдельно | `.shellcheckrc`, inline directives, shebang, CLI `--shell`; scripts без `.sh` тоже входят в scope | `shellcheck scripts/ci.sh`. Для всех scripts нужен безопасный selector; `.shellcheckrc` необязателен при принятом default-профиле |

Не нужно устанавливать все инструменты из строки. Например, Ruff и Flake8 могут дублировать многие правила; две конфликтующие formatter-конфигурации добавят шум. Сравниваются классы покрываемых рисков и эффективные правила. Новый инструмент не получает дополнительные баллы только за своё наличие.

### Дополнительные файлы, которые часто забывают

Эти направления обнаруживаются независимо от основного языка сервиса: Python-проект может содержать критичные Dockerfiles, SQL и shell scripts.

| Файлы / язык | Инструмент | Признаки конфигурации и предмет проверки |
| --- | --- | --- |
| SQL | [SQLFluff](https://docs.sqlfluff.com/en/stable/configuration/setting_configuration.html) | `.sqlfluff`, `[tool.sqlfluff]` в `pyproject.toml`, возможные INI-конфиги; обязательны правильный dialect и templater; `sqlfluff lint` |
| CSS / SCSS | [Stylelint](https://stylelint.io/user-guide/configure/) | `stylelint.config.*`, `.stylelintrc.*`, `package.json`; parser/custom syntax и совместимые presets; Prettier его не заменяет |
| YAML | [yamllint](https://yamllint.readthedocs.io/en/stable/configuration.html) | `.yamllint`, `.yamllint.yaml`, `.yamllint.yml`, CLI config; YAML style/syntax не проверяет бизнес-семантику CI или Kubernetes |
| Dockerfile | [Hadolint](https://github.com/hadolint/hadolint) | `.hadolint.yaml`, `.hadolint.yml`, inline ignores и CLI thresholds; инструкции Dockerfile и поддерживаемые shell checks |
| Terraform | [TFLint](https://github.com/terraform-linters/tflint) | `.tflint.hcl`, provider plugins и их версии; `terraform fmt/validate` — отдельные дополняющие этапы |
| Markdown | [markdownlint](https://github.com/DavidAnson/markdownlint) | `.markdownlint.*`, конфигурация выбранного CLI, например markdownlint-cli2; markdown parser и правила стиля |

## 4. Какие признаки искать для pre-commit и CI

| Механизм | Файлы / настройки | Какое доказательство нужно |
| --- | --- | --- |
| [pre-commit](https://pre-commit.com/) | `.pre-commit-config.yaml`: `repos`, `rev`, `hooks`, `entry`, `args`, `files`, `types`, `exclude`, `stages`, `additional_dependencies` | Конкретный lint-hook доступен для нужных файлов; есть инструкция/bootstrap установки. Успешный `pre-commit run --all-files` подтверждает запуск набора, но не установку hook у всех разработчиков |
| [Husky](https://typicode.github.io/husky/get-started.html) + [lint-staged](https://github.com/lint-staged/lint-staged) | `.husky/pre-commit`, `package.json` scripts, lint-staged config: `.lintstagedrc*`, `lint-staged.config.*` либо поле `lint-staged` | Скрипт hook вызывает нужную команду, glob соответствует файлам, зависимости установлены; одно наличие Husky не доказывает вызов линтера |
| [Lefthook](https://github.com/evilmartians/lefthook) | `lefthook.yml/yaml` и поддерживаемые версией альтернативы; `pre-commit` commands/jobs | Разрешить реальную конфигурацию и scripts; проверить условия запуска и scope |
| Собственные Git hooks | Версионируемая директория hooks, bootstrap и `core.hooksPath` | Проверяемый способ установки; `.git/hooks` не является переносимой конфигурацией репозитория |
| GitLab CI | `.gitlab-ci.yml`, `include`, `extends`, `rules`, `workflow`, scripts и child pipelines | Разрешённый граф CI + реальные jobs на MR SHA, exit codes, reports, `allow_failure` и merge settings |
| GitHub Actions / другая CI | `.github/workflows/*`, reusable workflows или эквивалентные build configs | Аналогичный путь от trigger до команды и required status check; `continue-on-error` и skips оцениваются отдельно |

Pre-commit ускоряет обратную связь, но разработчик может пропустить локальный hook. Для обязательного контроля нужен серверный gate. Тяжёлый линтер может запускаться только в CI; отсутствие локального hook тогда не должно автоматически давать FAIL. Наличие CI без pre-commit и наличие pre-commit без CI — разные состояния.

## 5. Проверки LT01–LT16

Важность — рекомендуемая полезность для внутреннего production-проекта. WARN/FAIL определяются профилем, а недоступные evidence дают UNKNOWN. NOT_APPLICABLE требует причины.

| ID | Проверка | Критерий и evidence | Важность |
| --- | --- | --- | ---: |
| LT01 | Language and linter coverage | Для всех поддерживаемых языков/компонентов найден подходящий инструмент или обоснованное исключение. Сопоставить tracked files, manifests и language/tool support; установленный tool без связи с языковым scope недостаточен | 5/5 |
| LT02 | Effective configuration declared | Найдена реально используемая конфигурация: локальная, встроенная в manifest, shared package/CLI flags либо явно принятые defaults закреплённой версии. Простое отсутствие отдельного файла не означает FAIL | 4/5 |
| LT03 | Configuration resolves successfully | Установленная версия понимает конфиг, плагины и наследование разрешаются, target language/runtime подходит. Подтверждённый invalid config — FAIL; ошибка окружения аудитора — UNKNOWN | 4/5 |
| LT04 | Meaningful rules enabled | Включён согласованный baseline правил; обязательные правила не выключены глобально/для всего production-кода. Число правил само по себе не рейтинг качества. Не требовать одинаковых rule IDs от разных инструментов | 5/5 |
| LT05 | Source scope is covered | Реальная выборка включает нужные source/tests/scripts и monorepo services. Проверить globs, ignores, working directory, build targets и file lists. «0 файлов проверено» при существующем обязательном scope не является PASS | 5/5 |
| LT06 | Reproducible toolchain | Версии линтеров, plugins, shared configs и нужного runtime воспроизводимы; установка использует lock/pin. Изменение rule defaults между версиями не должно происходить незаметно | 4/5 |
| LT07 | Documented local lint command | Есть переносимая команда вроде `make lint`, `npm run lint`, task/build goal, вызывающая тот же нормативный набор; описаны prerequisites, cwd и check/fix режимы | 3/5 |
| LT08 | Local hook integration | Поддерживаемый механизм pre-commit/pre-push действительно вызывает нужные быстрые проверки; есть путь установки. Configured не означает установку у каждого разработчика. CI-only профиль допускается | 3/5 |
| LT09 | Lint runs in CI for relevant changes | Для MR с применимыми изменениями запущены ожидаемые lint jobs. Изменение lint-конфига, shared preset, lockfile или build settings также запускает затронутый scope | 5/5 |
| LT10 | Lint passes on evaluated revision | Линтер завершился на оцениваемой ревизии, выполнил требуемую область и не обнаружил нарушений выше принятого порога. Использовать tool result и reports, а не только общий pipeline status | 5/5 |
| LT11 | Lint failure blocks merge | Нарушение нормативного порога не маскируется `allow_failure`, `continue-on-error`, `\|\| true`, неправильным pipe exit code или необязательной manual job; required check относится к нужной ревизии | 5/5 |
| LT12 | Formatting checked separately | Если форматирование входит в политику, formatter работает в check/diff режиме и обнаруженные изменения дают нужный exit status. Успешный автоматический fix без проверки исходного состояния не подтверждает чистоту исходного commit | 3/5 |
| LT13 | Local and CI policies agree | Версии, presets, flags и scope согласованы; local hooks могут проверять staged subset, но не противоречат CI. Отдельная тяжёлая CI-проверка допустима и документируется | 4/5 |
| LT14 | Suppressions and baseline controlled | У широких ignores/baselines есть причина, owner и условия пересмотра; новые подавления и рост baseline видны в diff. Не штрафовать любое `noqa`/disable без анализа назначения | 4/5 |
| LT15 | Actionable lint reports | Доступны rule ID, message, path/line, severity, revision и tool version; предпочтителен JSON/SARIF или Code Quality report. Reports доступны и при failure; отсутствие findings не равно отсутствию запуска | 3/5 |
| LT16 | Lint policy changes reviewed | Конфиги, suppressions, wrappers, hook definitions, зависимости и CI lint jobs покрыты ответственными owners/review. Изменение правил в самом MR не должно незаметно убрать проверяемый контроль | 4/5 |

### Разбор LT02: наличие файла и наличие политики

| Ситуация | Предлагаемый результат LT02 |
| --- | --- |
| Конфиг существует, применяется к нужному scope и хранится под version control | PASS; запуск оценивается отдельно |
| Используются defaults закреплённой версии, этот выбор явно описан и воспроизводим | PASS, `configuration_mode: defaults` |
| Правила приходят из закреплённого shared config, цепочка разрешена | PASS, `configuration_mode: shared` |
| Отдельного файла нет, а выбрать defaults или policy невозможно по evidence | WARN при подтверждённом неявном процессе либо UNKNOWN при недостатке данных |
| Файл есть, но команда использует другую конфигурацию | Оценить фактически используемую политику; неиспользуемый файл — отдельная находка |
| Инструмент требует конфиг, но он подтверждённо отсутствует | FAIL |

Для Ruff вложенный конфиг не обязательно автоматически объединяется с родительским; для ESLint важны версия и формат конфигурации. Детектор должен применять правила самого инструмента, а не один общий алгоритм поиска «ближайшего YAML». [Ruff configuration](https://docs.astral.sh/ruff/configuration/), [ESLint configuration](https://eslint.org/docs/latest/use/configure/configuration-files).

### Разбор LT09–LT11: запуск, результат и обязательность

| Ситуация | LT09: запускается | LT10: проходит | LT11: блокирует merge |
| --- | --- | --- | --- |
| Job выполнилась, lint чист, required gate подтверждён | PASS | PASS | PASS |
| Job выполнилась, найдены запрещённые нарушения, gate обязателен | PASS | FAIL | PASS |
| Job выполнилась, lint чист, но `allow_failure: true` | PASS | PASS | FAIL для обязательного профиля |
| Job должна была запуститься для MR, но подтверждённо пропущена из-за rules | FAIL | UNKNOWN — нет результата | FAIL, если merge допускается без неё; иначе отдельная оценка |
| Runner недоступен, pipeline pending | UNKNOWN для ещё не состоявшегося запуска | UNKNOWN | Оценка настройки отдельно; недоступность runner не доказывает обход |
| Отчёт потерян, подробные логи/exit status инструмента недоступны | По сохранившимся job events | UNKNOWN | По effective merge settings |

Синтаксическая ошибка исходников, сообщённая работающим линтером, — нарушение проверяемого кода. Невозможность запустить линтер из-за несовместимого config подтверждает проблему LT03, но не позволяет объявить исходники прошедшими LT10.

## 6. Алгоритм для реализации

1. Построить inventory tracked files по языкам и компонентам. Отдельно учитывать authored/generated/vendor code, tests, migrations и scripts без расширений.
2. Найти кандидатов tools/configs/dependencies/commands/hooks/CI definitions. Наличие строки `eslint` или `ruff` даёт только candidate detection.
3. Разрешить реальную команду: wrappers, package scripts, task dependencies, CI includes/extends, cwd, CLI overrides и environment.
4. Определить effective config для каждого scope: версии, sources, rule presets, severity, include/exclude, runtime/build targets и suppressions.
5. Проверить реальное покрытие: ожидаемый список файлов против обработанного. Если инструмент не отдаёт file list, применять adapter-supported listing/debug или изолированную верификацию; отсутствие findings не доказывает обработку каждого файла.
6. Получить job/report evidence на нужном commit SHA либо merged-result revision; сохранить тип ревизии и её связь с MR.
7. Независимо проверить merge gate и возможности обхода. Нынешняя настройка gate не доказывает обязательность для прошлых MR.
8. Выдать LT-результаты по scope, объяснение пробелов и конкретное действие. Отсутствие adapter support — UNKNOWN, а не отсутствие линтера.

Executable configs и plugins могут выполнять код: ESLint JS/TS config, R `.lintr`, shared packages, Gradle/build scripts. Статическое чтение не должно незаметно переходить в их исполнение. Разрешение через сам инструмент выполняется в изолированной среде без production credentials; сборщик предпочитает уже существующие CI evidence. Конфиг R действительно может содержать вычисляемые R-выражения. [lintr configuration](https://lintr.r-lib.org/articles/lintr.html).

### Monorepo и инкрементальные проверки

Нельзя присваивать всему monorepo PASS по одной job в одном сервисе. Минимальный ключ результата: `(check_id, component, language, tool, revision)`.

Локальный hook обычно проверяет staged files, CI может проверять изменённые или все файлы. Для diff-only lint нужны корректный merge base, учёт renames и распространение изменений общей конфигурации на все затронутые компоненты. Для semantic/type-aware анализаторов список изменённых файлов не обязательно покрывает последствия изменения типов и зависимостей.

Допустимы два профиля: полный анализ каждого MR либо инкрементальный MR-анализ с регулярным полным сканированием и определённым TTL. В отчёте явно указывается, какой уровень покрытия подтверждён; локальная проверка нескольких файлов не объявляется полным сканированием.

## 7. Предлагаемое evidence

Помимо общей модели результата хранить:

| Поле | Назначение |
| --- | --- |
| `tool.name`, `tool.version`, `tool.role` | Конкретный инструмент, версия и роль: lint/format/static-analysis |
| `runtime`, `plugins`, `shared_configs` | Фактическое окружение и версии зависимостей правил |
| `configuration_mode`, `config_paths`, `effective_config_hash` | Файлы/defaults/shared policy и идентификатор эффективной конфигурации |
| `command`, `working_directory`, `scope` | Что запускалось и из какой директории; секретные arguments редактируются |
| `expected_files`, `analyzed_files`, `excluded_files`, `coverage_known` | Проверенное покрытие; если список неизвестен, не подставлять ожидаемое число вместо реального |
| `revision`, `revision_kind`, `pipeline_id`, `job_id` | Связь с commit/MR и CI execution |
| `tool_exit_code`, `job_status`, `threshold`, `findings_counts` | Сырой результат, состояние wrapper и применение severity policy |
| `report_uri`, `collected_at`, `expires_at` | Evidence и срок его актуальности/доступности |

GitLab умеет принимать результаты инструментов в Code Quality report; наличие отчёта само по себе не делает проверку обязательным merge gate. Для интеграции предпочтителен прямой экспорт/конвертация findings существующего линтера. [GitLab Code Quality](https://docs.gitlab.com/ci/testing/code_quality/).

## 8. Связь с существующими проверками и scoring

Q06 сохраняется как обзор «Lint and formatting». В расширенном профиле он вычисляется из LT01–LT16 и отображается со `scoring_enabled: false`, чтобы один контроль не приносил баллы дважды. В компактном профиле можно оценивать только Q06; тогда LT-детализация не входит в агрегат.

| Существующие ID | Пересечение | Как не считать дважды |
| --- | --- | --- |
| Q06 | Общая оценка линтинга/форматирования | Q06 — обзор без отдельного веса в расширенном профиле |
| Q01 / G06 | CI запускается / успешные проверки обязательны | LT09/LT11 — конкретный scope lint; общий контроль имеет ограниченный вес или исключает этот подscope |
| Q07 / Q08 | Статический анализ / SAST | Одна и та же finding и execution сохраняются один раз; роли tools явно отмечены |
| S06 / S07 | Воспроизводимость dependencies/tools | LT06 переиспользует evidence; профиль распределяет общий вес |
| G07 | Review конфигурации CI | LT16 добавляет configs/suppressions/wrappers и использует общие effective owner rules |

Покрытие языков/компонентов агрегируется с заранее заданными весами и рядом с assessment coverage. Критичный сервис без lint не должен исчезать за большим числом проверенных маленьких пакетов.

## 9. Минимальный набор внедрения

Первая итерация: **LT01, LT02, LT05, LT09, LT10, LT11** — подходящий инструмент, применимая политика, покрытие, запуск, результат и обязательность.

Далее: **LT03, LT06, LT07, LT08, LT13** — воспроизводимый и удобный developer workflow. Затем: **LT04, LT12, LT14, LT15, LT16** — развитие rules policy, formatter, контроль исключений, отчёты и защита правил. LT04 и LT16 можно поднять в первую итерацию для критичных сервисов.

Для Python-монорепозитория разумная отправная точка — Ruff check и отдельный Ruff format check, общий конфиг с осознанными service overrides, быстрые hooks и обязательный CI. Нужные дополнительные проверки Pylint/mypy остаются отдельными требованиями; Ruff не объявляется их полной заменой.

Для JS/TS — ESLint + typescript-eslint с presets под используемый framework, либо Biome после проверки нужных правил и file support. [Prettier](https://prettier.io/docs/configuration) — отдельный formatter, если выбранный процесс его использует. Наличие одновременно ESLint, Biome и Prettier не является требованием методологии.

## 10. Проверка самого детектора

При реализации нужны случаи: валидные defaults без конфига; неиспользуемый конфиг; nested overrides; missing plugin; правильный command из неправильного cwd; 0 обработанных файлов; новый сервис без job; config-only MR; skipped/manual/allow-failure job; обнулённый exit code; stale report; local/CI version mismatch; baseline, скрывающий все findings; framework-файлы вне glob; недоступный CI API.

Для проверки LT11 можно использовать контролируемое нарушение в тестовом fixture детектора. Не следует делать пробный ошибочный push в рабочий репозиторий. Эти сценарии описывают будущую верификацию реализации, а не результаты выполненного аудита проекта.
