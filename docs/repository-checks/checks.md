# lct-git-score: каталог проверок здоровья репозитория

Статус: предлагаемый каталог, версия 0.1. Дата: 2026-09-09.

Связанный документ: [подход, оценка и правила интерпретации](approach.md). Детализация линтинга: [linting.md](linting.md).

Каталог включает 88 проверок. ID стабильны и пригодны для конфигурации, API, ссылок на находки и будущих страниц сайта. Наличие проверки в каталоге не означает, что она уже реализована. Блок LT01–LT16 подробно описан в [linting.md](linting.md).

## Как читать каталог

Основной контекст — внутренний production-репозиторий GitLab. Рейтинг 5/5 означает наибольшую рекомендуемую важность, 4/5 — высокую ценность, 3/5 — зависимость от контекста, 2/5 — преимущественно удобство или соглашение, 1/5 — косметический эффект. Это проектный рейтинг, а не балл внешнего стандарта.

Первая категория определяется группой таблицы; дополнительные категории раскрывают пересечения. В колонке реализации приведён канонический инструмент или пример способа получения evidence. Если готового стандарта нет, указан собственный анализ. Инструмент не гарантирует полного покрытия описанной проверки.

Для нормативных проверок используются PASS, WARN, FAIL, NOT_APPLICABLE и UNKNOWN по правилам методологии. У измерений без согласованного порога — `evaluation_mode: observation`, `status: null`, `score: null`. Значение метрики само по себе не является нарушением.

Для каждой проверки сохраняются время, scope, версия алгоритма/политики, источник и полнота данных. Отсутствие доступа не приравнивается к отсутствию контроля. Пороги размера, возраста, coverage, задержек и частот настраиваются по профилю проекта.

## R. Целостность и гигиена Git — 8 проверок

| ID | Краткое название | Дополнительные категории | Что проверять и как трактовать | Реализация / evidence | Важность |
| --- | --- | --- | --- | --- | ---: |
| R01 | Git object integrity | Надёжность | Связность и корректность доступных объектов. Повреждённые/отсутствующие обязательные объекты — FAIL; dangling objects сами по себе не означают повреждение. Сохранять полноту clone и refs | [`git fsck --full --strict`](https://git-scm.com/docs/git-fsck), разбор диагностик | 5/5 |
| R02 | Valid default branch | Управление | Ветка, объявленная default на сервере, существует и разрешается в commit. Для активного проекта пустая/отсутствующая ветка — FAIL; новый ещё не инициализированный проект требует отдельного профиля | [Projects API](https://docs.gitlab.com/api/projects/), [Branches API](https://docs.gitlab.com/api/branches/); локальный `origin/HEAD` только вспомогательный источник | 5/5 |
| R03 | Repository size | Производительность | Размер объектов, packfiles и рост относительно прошлых снимков. WARN/FAIL только по политике; сетевой размер clone и размер сервера хранить отдельно | [`git count-objects -vH`](https://git-scm.com/docs/git-count-objects), [git-sizer](https://github.com/github/git-sizer), GitLab Projects API с `statistics=true` при доступных правах | 3/5 |
| R04 | No large tracked files | Производительность | Blobs превышают лимит текущего дерева или доступной истории; отчёт различает новые и исторические нарушения. Для разрешённых крупных активов использовать подходящий storage | [git-sizer](https://github.com/github/git-sizer); `git rev-list --objects --all` + `git cat-file --batch-check`; [Git LFS](https://git-lfs.com/) как способ исправления | 4/5 |
| R05 | Artifact hygiene | Качество, безопасность | Среди tracked files нет запрещённых дампов, cache, логов, credentials и случайных build outputs. `.env.example` и необходимые generated assets допускаются политикой. `.gitignore` не удаляет уже tracked files | `git ls-files`, собственные правила путей/типов; [pre-commit-hooks](https://github.com/pre-commit/pre-commit-hooks) для части preventive checks | 4/5 |
| R06 | Binary/generated code ratio | Поддерживаемость | Доля binary, vendor и generated files по байтам и количеству; рост — повод проверить назначение. Универсального допустимого процента нет | [Linguist](https://github.com/github-linguist/linguist), `.gitattributes`, собственная классификация | 3/5 |
| R07 | Valid submodules | Supply chain | Gitlinks указывают на доступные commits; URLs разрешены политикой; нет неожиданных вложенных источников. Недоступность из-за прав — UNKNOWN, подтверждённый потерянный commit — FAIL | `.gitmodules`, `git ls-tree`, [`git submodule status --recursive`](https://git-scm.com/docs/git-submodule), проверка доступности через доверенный collector | 4/5 |
| R08 | Repository maintenance | Производительность | Аномальный объём loose objects/refs и признаки необходимости housekeeping. Локальные показатели не описывают автоматически серверное хранилище | `git count-objects -v`, `git for-each-ref`, server housekeeping statistics; [`git maintenance`](https://git-scm.com/docs/git-maintenance) — возможная рекомендация, не действие аудитора | 2/5 |

### Ограничения Git-проверок

`fsck` проверяет доступную объектную базу. Успех в shallow/partial clone не подтверждает полноту всей истории сервера. Strict-диагностики анализируются по типу: историческая несовместимость формата и повреждение данных имеют разные последствия. Нельзя объявлять FAIL по одному лишь наличию вывода в stderr. [Git fsck](https://git-scm.com/docs/git-fsck).

LFS pointers не доказывают наличие самих LFS objects. Для используемого LFS нужна отдельная проверка доступности содержимого в рамках R04. Submodule уже закреплён gitlink SHA; настройка tracking branch в `.gitmodules` не отменяет закрепление checkout, но использование `update --remote` во время сборки может сделать входы изменяемыми.

## D. Документация, ownership и управление — 10 проверок

| ID | Краткое название | Дополнительные категории | Что проверять и как трактовать | Реализация / evidence | Важность |
| --- | --- | --- | --- | --- | ---: |
| D01 | Useful README | Onboarding | Описаны назначение, локальный запуск, конфигурация, тесты и владелец; для сервиса есть ссылка на deployment/runbook. Проверять содержательность и ссылки, а не только существование заголовков | `README.md`, правила разделов и ссылок; [Community Profile](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories) как базовый ориентир | 5/5 |
| D02 | Explicit ownership | Устойчивость | У репозитория и критичных компонентов указаны существующие ответственные команды/люди и канал связи. Неактивная либо несуществующая группа не считается полноценным владельцем | `CODEOWNERS`, `MAINTAINERS.md`, service catalog; сверка с доступной directory/group information | 5/5 |
| D03 | CODEOWNERS coverage | Review | Доля production files, совпавших с действительными owner rules; критичные пути проверяются отдельно. Общий wildcard может давать 100% формального покрытия без распределения ответственности | [GitLab CODEOWNERS](https://docs.gitlab.com/user/project/codeowners/), provider-specific parser и `git ls-files` | 5/5 |
| D04 | Contribution guide | Процесс | Описаны setup, проверки, MR flow, стиль, миграции и релизы в применимой области; допустима ссылка на актуальный общий стандарт | `CONTRIBUTING.md`, доступные linked docs, правила обязательных тем | 4/5 |
| D05 | Security policy | Безопасность | Понятны канал сообщения об уязвимости, ответственный и поддерживаемые версии/сервисы. Для внутреннего проекта допустима корпоративная процедура | `SECURITY.md` или доступная ссылка; OpenSSF `Security-Policy` как пример | 4/5 |
| D06 | Production runbook | Эксплуатация | Есть диагностика, health checks, dashboards, alerting, rollback, миграции и аварийные контакты. Внешний актуальный runbook допустим; отсутствие доступа к нему — UNKNOWN | `RUNBOOK.md`, `docs/operations.md`, service catalog; структурная проверка + подтверждение владельцем | 5/5 production |
| D07 | Architecture documentation | Поддерживаемость | Описаны границы компонентов, внешние зависимости и значимые решения. Возраст документа — повод проверить актуальность, но не самостоятельное доказательство устаревания | `docs/architecture.md`, [ADR](https://adr.github.io/), сопоставление с изменениями компонентов | 3/5 |
| D08 | License declared | Права использования, supply chain | Указан применимый режим использования кода. Для OSS — явно объявленная лицензия; для внутреннего кода — корпоративный proprietary notice/политика при необходимости. Проверка не определяет юридическую достаточность | `LICENSE`, [REUSE](https://reuse.software/), [SPDX identifiers](https://spdx.org/licenses/) | 2/5 internal; 5/5 OSS |
| D09 | MR/issue templates | Процесс | Шаблоны помогают описать цель, тестирование, риски и rollback. Наличие шаблона и фактическое заполнение MR — разные результаты | [GitLab description templates](https://docs.gitlab.com/user/project/description_templates/), выборка MR/issue descriptions | 3/5 |
| D10 | Service metadata | Эксплуатация | Машиночитаемо заданы команда, lifecycle, критичность, runtime, зависимости и эксплуатационные ссылки; значения согласованы с каталогом | [Backstage descriptor](https://backstage.io/docs/features/software-catalog/descriptor-format/), `catalog-info.yaml` либо `service.yaml` со схемой проекта | 4/5 |

### Ownership: три разных вопроса

D02 отвечает, назначен ли владелец; D03 — покрывают ли правила нужный код; G05 — требуется ли его approval. T03 добавляет наблюдение о реальном участии людей. Эти результаты показываются рядом, но не заменяют друг друга.

Для D03 следует использовать семантику конкретного провайдера: порядок шаблонов, секции, optional rules, права и допустимость owners. Произвольный glob matcher может дать ошибочное покрытие. Отдельно сохраняются доля сопоставленных файлов, доля с доступными владельцами и список критичных непокрытых путей.

## G. Защита истории и управление изменениями — 12 проверок

| ID | Краткое название | Дополнительные категории | Что проверять и как трактовать | Реализация / evidence | Важность |
| --- | --- | --- | --- | --- | ---: |
| G01 | Protected default branch | Безопасность | Default/release branches защищены в принятой модели полномочий; force push выключен; права удаления и изменения правил ограничены. Учитывать все совпавшие и унаследованные правила | [Protected Branches API](https://docs.gitlab.com/api/protected_branches/), [branch protection](https://docs.gitlab.com/user/project/repository/branches/protected/) | 5/5 |
| G02 | MR-only changes | Review | Обычным участникам нельзя напрямую push в защищённые ветки; bot/deploy-key исключения узкие и видимые. Настройки дополняются историей push/merge при её доступности | Effective push/merge permissions, protected branches, audit/push events | 5/5 |
| G03 | Independent approval | Безопасность | Требуется независимый человек; автор MR и участники изменения не могут единолично подтвердить собственную работу; правила нельзя ослабить внутри MR. Проверяется применимая ревизия | [GitLab approval settings](https://docs.gitlab.com/user/project/merge_requests/approvals/settings/), [approvals API](https://docs.gitlab.com/api/merge_request_approvals/) | 5/5 |
| G04 | Fresh approval | Review | Изменения после approval требуют повторной проверки согласно политике: всей ревизии либо затронутых owner paths. Сохранять момент изменения и approvals | Reset/remove approvals settings, MR versions и approval events | 4/5 |
| G05 | Required CODEOWNER review | Ownership | Для критичных файлов требуется approval допустимого владельца и отсутствует обычный обход через direct push или optional section | [Code Owner approvals](https://docs.gitlab.com/user/project/codeowners/), protected branches, effective approval rules | 5/5 |
| G06 | Required status checks | CI/CD, качество | Merge блокируется при отсутствующей/неуспешной обязательной проверке релевантного MR SHA или merged-result revision. Skipped/manual/allow-failure jobs не должны давать ложный PASS | [GitLab merge checks](https://docs.gitlab.com/user/project/merge_requests/auto_merge/#require-a-successful-pipeline-for-merge), Projects API, pipelines/jobs и CI rules | 5/5 |
| G07 | Protected CI configuration | Supply chain, ownership | CI definitions, includes, Dockerfiles, deployment scripts и IaC входят в критичные пути; их изменение требует специальных approvals. Общие внешние шаблоны также имеют контролируемый источник | CODEOWNERS + effective approvals; инвентаризация локальных и внешних CI/config inputs | 5/5 |
| G08 | Immutable release tags | Release, supply chain | Release tag нельзя незаметно переназначить или удалить в заданной модели прав; privileged exceptions и история изменений видимы | [Protected tags](https://docs.gitlab.com/user/project/protected_tags/), push rules, audit events, снимки tag → SHA | 4/5 |
| G09 | Verified commit identity | Audit | Отдельно оцениваются соответствие identity корпоративной политике и криптографическая проверка подписи. Email не подтверждает авторство; валидная подпись требует доверенной identity | [GitLab push rules](https://docs.gitlab.com/user/project/repository/push_rules/), GPG/SSH signature verification и trust policy | 3/5 |
| G10 | Change traceability | Процесс | Изменение имеет доступную причину: issue, incident, задача или содержательное обоснование MR. Формальная ссылка на несуществующий issue недостаточна | MR description/links, commit references, собственный validator | 3/5 |
| G11 | Consistent merge strategy | Release | Принята стратегия squash/merge/rebase и правила реально ей соответствуют. Допустимые исключения описаны; одна стратегия не объявляется лучшей для всех | Project merge/squash settings, CONTRIBUTING, структура истории | 3/5 |
| G12 | Stale branch control | Гигиена | Показывать старые merged и неактивные ветки отдельно; исключать постоянные release/support branches. Удаление — рекомендация владельцу | Branches API, last commit, merged state, naming/lifecycle policy | 2/5 |

### Enforcement и ограничения платформы

Protected branch/tag ограничивает действия, но не доказывает абсолютную неизменяемость для администратора. В GitLab удаление protected tags возможно для разрешённых ролей через предусмотренные интерфейсы. Для G08 проверяются эффективные права и аудит; одного признака `protected` недостаточно. [GitLab protected tags](https://docs.gitlab.com/user/project/protected_tags/).

Независимость G03 — требование политики проекта. GitLab отдельно позволяет ограничивать approvals автора и пользователей, добавивших commits; rebase может повлиять на определение committers. Нельзя обещать доказательство независимости всех участников только по одному полю настройки. [Approval settings](https://docs.gitlab.com/user/project/merge_requests/approvals/settings/).

## Q. CI, тестирование и качество кода — 10 проверок

| ID | Краткое название | Дополнительные категории | Что проверять и как трактовать | Реализация / evidence | Важность |
| --- | --- | --- | --- | --- | ---: |
| Q01 | CI on every MR | Процесс | Для каждого подходящего MR и проверяемой ревизии запускается ожидаемая pipeline. Считать долю с CI; YAML сам по себе не доказательство. Правила исключений должны быть явными | [Pipelines API](https://docs.gitlab.com/api/pipelines/), MR pipelines, SHA, sources и timestamps | 5/5 |
| Q02 | Automated tests | Тестирование | Реально выполнены необходимые тесты; есть число tests/failures/skips и машиночитаемый результат. Пустой report или один job с названием test не дают PASS | [GitLab unit test reports](https://docs.gitlab.com/ci/testing/unit_test_reports/), JUnit XML, `pytest --junitxml=report.xml` | 5/5 |
| Q03 | Default branch green | Стабильность | Последняя обязательная завершённая pipeline актуальной ветки успешна; отдельно измеряются текущая незавершённая pipeline и время в красном состоянии. Старый success не доказывает состояние нового HEAD | Pipelines/jobs API, revision match, история переходов состояния | 5/5 |
| Q04 | Coverage reporting | Тестирование | Coverage актуальна и относится к нужному scope; показывать общий trend и coverage изменённых строк. Пороги и допустимое падение определяет команда | [GitLab coverage](https://docs.gitlab.com/ci/testing/code_coverage/), Cobertura, coverage.py, [diff-cover](https://github.com/Bachmann1234/diff_cover) | 4/5 |
| Q05 | Flaky test rate | Стабильность | Есть tests с различными исходами при сопоставимом коде, inputs и окружении; отделять подтверждённую нестабильность от подозрения и инфраструктурных сбоев | Testcase history, JUnit XML, job attempts, environment fingerprint, quarantine registry | 5/5 |
| Q06 | Lint and formatting | Качество | Обзор линтинга и форматирования. В расширенном профиле вычисляется из LT01–LT16 и не даёт отдельный вес. Локальный hook без CI — только дополнительный механизм | [linting.md](linting.md); [pre-commit](https://pre-commit.com/), [Ruff](https://docs.astral.sh/ruff/), ESLint и CI reports | 4/5 |
| Q07 | Type/static checks | Качество | Для применимого языка выполняются type/compile checks; видны scope, конфигурация и исключения. Массовые ignores не должны скрывать отсутствие покрытия | [mypy](https://mypy.readthedocs.io/), Pyright, TypeScript compiler, native compiler reports | 4/5 |
| Q08 | SAST present | Безопасность | Scanner действительно анализирует нужный код свежими правилами; findings обрабатываются по политике. Конфиг без успешного запуска не подтверждает работающий контроль | [Semgrep](https://semgrep.dev/docs/), CodeQL, [GitLab SAST](https://docs.gitlab.com/user/application_security/sast/) | 4/5 |
| Q09 | Complexity and duplication | Поддерживаемость | Растущая сложность, duplication и крупные модули; акцент на изменяемом коде и trend. Сравнения между языками требуют нормализации | [Radon](https://radon.readthedocs.io/), SonarQube, PMD/CPD; собственная агрегация | 3/5 |
| Q10 | CI feedback time | Эффективность | p50/p85 времени от принятой точки старта до результата обязательных проверок; queue и execution показываются отдельно. Pipeline-level duration не всегда отражает ожидание автора | Pipelines/jobs timestamps, очередь runner и critical-path calculation | 4/5 |

### Тесты и качество данных

Для Q05 единица наблюдения — test case при конкретной ревизии, конфигурации и окружении. Отчёт показывает число сопоставимых повторов, test cases с расхождением и долю tests, для которых вообще были повторы. Повтор failed job, ставший успешным, — кандидат на анализ, но не достаточное доказательство flaky test. Если есть только job-level сведения, результат помечается proxy и не называется точной test-level rate.

Истёкший JUnit/coverage artifact даёт UNKNOWN по недостающему факту. Подтверждённое отсутствие запуска тестов даёт FAIL. Quarantined tests показываются отдельно; их исключение из CI не должно искусственно улучшать наблюдаемую надёжность.

Q06 не дублирует баллы LT-блока: в расширенном профиле это обзор со `scoring_enabled: false`. Детальные критерии линтеров — LT01–LT16.

## LT. Линтинг и линтеры — 16 проверок

| ID | Краткое название | Дополнительные категории | Что проверять и как трактовать | Реализация / evidence | Важность |
| --- | --- | --- | --- | --- | ---: |
| LT01 | Language and linter coverage | Качество | Для всех поддерживаемых языков/компонентов найден подходящий инструмент или обоснованное исключение. Установленный tool без связи с языковым scope недостаточен | Сопоставление tracked files, manifests и конфигов инструментов; [linting.md](linting.md) | 5/5 |
| LT02 | Effective configuration declared | Качество | Найдена реально используемая конфигурация: локальная, встроенная в manifest, shared package/CLI flags либо явно принятые defaults закреплённой версии. Отсутствие отдельного файла само по себе не FAIL | Конфиги инструментов, pyproject/package scripts, pinned defaults | 4/5 |
| LT03 | Configuration resolves successfully | Качество | Установленная версия понимает конфиг, плагины и наследование разрешаются. Подтверждённый invalid config — FAIL; ошибка окружения аудитора — UNKNOWN. Executable-конфиги не исполняются сборщиком | Статический разбор JSON/TOML/YAML; изолированный запуск инструмента — отдельный источник | 4/5 |
| LT04 | Meaningful rules enabled | Качество | Включён согласованный baseline; обязательные правила не выключены глобально для production-кода. Число правил — не рейтинг качества | Preset/extends/select, отсутствие `ignore ALL` / пустого ruleset | 5/5 |
| LT05 | Source scope is covered | Качество | Выборка включает нужные source/tests/scripts и сервисы monorepo. «0 файлов проверено» при обязательном scope — не PASS | Globs, ignores, working directory, file lists | 5/5 |
| LT06 | Reproducible toolchain | Воспроизводимость | Версии линтеров, plugins, shared configs и runtime воспроизводимы; установка использует lock/pin | lockfiles, pre-commit `rev`, rust-toolchain, go.mod; пересечение с S06/S07 | 4/5 |
| LT07 | Documented local lint command | Процесс | Есть переносимая команда (`make lint`, `npm run lint`, task/goal) того же нормативного набора; описаны prerequisites, cwd, check/fix | Makefile, package.json scripts, just/tox, README | 3/5 |
| LT08 | Local hook integration | Процесс | pre-commit/pre-push/Husky/Lefthook вызывает быстрые проверки либо документирован CI-only профиль. Configured ≠ установлено у каждого разработчика | `.pre-commit-config.yaml`, `.husky/`, `lefthook.yml` | 3/5 |
| LT09 | Lint runs in CI for relevant changes | CI/CD | Для MR с применимыми изменениями запущены ожидаемые lint jobs, включая смену lint-конфига/lockfile. YAML без запуска — не PASS | CI YAML + pipelines/jobs API на SHA | 5/5 |
| LT10 | Lint passes on evaluated revision | Качество | Линтер завершился на оцениваемой ревизии, покрыл требуемую область и не превысил порог. Синтаксическая ошибка исходников — нарушение кода, не LT03 | Tool exit code, JSON/SARIF/Code Quality report | 5/5 |
| LT11 | Lint failure blocks merge | CI/CD | Нарушение порога не маскируется `allow_failure`, `continue-on-error`, `\|\| true` или manual job; required check относится к нужной ревизии | Merge checks, job `allow_failure`, required status | 5/5 |
| LT12 | Formatting checked separately | Качество | Если форматирование в политике, formatter работает в check/diff режиме. Успешный auto-fix без проверки исходного commit не подтверждает чистоту | `ruff format --check`, prettier `--check`, `cargo fmt --check` | 3/5 |
| LT13 | Local and CI policies agree | Процесс | Версии, presets, flags и scope согласованы; local hooks могут проверять staged subset, но не противоречат CI | Сравнение hook config и CI commands | 4/5 |
| LT14 | Suppressions and baseline controlled | Качество | У широких ignores/baselines есть причина, owner и пересмотр; новые подавления видны в diff. Не штрафовать любое `noqa` без анализа | Ignore-файлы, baseline/TODO, inline suppressions | 4/5 |
| LT15 | Actionable lint reports | Качество | Доступны rule ID, message, path/line, severity, revision и tool version; JSON/SARIF или Code Quality. Пустой отчёт ≠ отсутствие запуска | CI artifacts, GitLab Code Quality | 3/5 |
| LT16 | Lint policy changes reviewed | Review | Конфиги, suppressions, wrappers, hooks и CI lint jobs покрыты owners. Изменение правил в самом MR не должно незаметно убрать контроль | CODEOWNERS + approval rules; пересечение с G07 | 4/5 |

### Как читать LT-блок

Первая итерация реализации: LT01, LT02, LT05, LT09, LT10, LT11. Отсутствие adapter support даёт UNKNOWN, а не «линтера нет». Нельзя присвоить всему monorepo PASS по одной job одного сервиса. Полная методология, shortlist инструментов и модель evidence — в [linting.md](linting.md).

Q07 (типы/статика) и Q08 (SAST) остаются отдельными: тот же finding не считается дважды; роли tools помечаются явно.

## S. Безопасность и software supply chain — 12 проверок

| ID | Краткое название | Дополнительные категории | Что проверять и как трактовать | Реализация / evidence | Важность |
| --- | --- | --- | --- | --- | ---: |
| S01 | Secret scanning | Безопасность | Отдельно сканируются текущее дерево, новые изменения и доступная история refs; findings проверяются и обрабатываются. Отчёт указывает scope, tool/rules version и дату; clean scan не гарантирует отсутствие всех секретов | [Gitleaks](https://github.com/gitleaks/gitleaks), [TruffleHog](https://github.com/trufflesecurity/trufflehog), provider secret scanning | 5/5 |
| S02 | Push secret protection | Безопасность | Серверный механизм отклоняет push с распознаваемыми secrets до включения в историю; обходы и исключения ограничены. CI после push и локальный pre-commit не эквивалентны | [GitLab secret push protection](https://docs.gitlab.com/user/application_security/secret_detection/secret_push_protection/), GitHub push protection или управляемый pre-receive scanner | 5/5 |
| S03 | Vulnerable dependencies | Зависимости | Fresh scan direct/transitive и применимых runtime/container dependencies; findings имеют severity, SLA, triage и risk acceptance. Просроченное обязательное исправление — FAIL | [OSV-Scanner](https://google.github.io/osv-scanner/), [Trivy](https://trivy.dev/), Grype, GitLab Dependency Scanning | 5/5 |
| S04 | Automated dependency updates | Поддерживаемость | Update automation запускается, создаёт релевантные MR, и очередь обрабатывается; конфиг без активности недостаточен. Допускается иной проверяемый процесс обновлений | [Renovate](https://docs.renovatebot.com/), Dependabot, schedules и история update MR | 4/5 |
| S05 | Dependency age | Поддерживаемость | Отставание от поддерживаемой ветки, EOL и security updates. Старый номер major сам по себе не нарушение; поддерживаемые LTS и backports учитываются | Package registry metadata, Renovate datasources, upstream support policy | 4/5 |
| S06 | Deterministic dependency resolution | Воспроизводимость | Для приложения зафиксировано разрешение зависимостей и CI использует режим без неявного обновления lockfile. Проверка учитывает экосистему и все модули monorepo | [uv lock/sync](https://docs.astral.sh/uv/concepts/projects/sync/), Poetry, `npm ci`, pnpm frozen lockfile; для Go — `go.mod` и модель modules, а не `go.sum` отдельно | 5/5 |
| S07 | Pinned CI dependencies | CI/CD | Внешние actions/includes, контейнеры и tools закреплены на immutable SHA/digest либо проверяемое содержимое; mutable tags/branches перечислены. Обновления pin должны быть управляемыми | OpenSSF `Pinned-Dependencies` как ориентир, CI parser, container digest, immutable include refs | 5/5 |
| S08 | Least CI permissions | CI/CD | Job/workflow tokens, secrets и runners имеют необходимые минимальные права по stage и trust level; protected variables и scope проверяются без чтения значений | [GitLab job tokens](https://docs.gitlab.com/ci/jobs/ci_job_token/), variable metadata, permissions, runner settings; OpenSSF `Token-Permissions` для поддерживаемой платформы | 5/5 |
| S09 | Dangerous workflow detection | CI/CD | Непроверенный MR-код не получает privileged execution; анализируются triggers, интерполяция входов, includes, artifacts/cache и переходы между untrusted и trusted jobs | CI data-flow/trust-boundary analysis, security scanner rules; OpenSSF workflow checks/probes как пример | 5/5 |
| S10 | SBOM generated | Release | SBOM привязан к digest конкретного артефакта, соответствует его составу и доступен для проверки. Устаревший SBOM исходников не подтверждает состав релиза | [Syft](https://github.com/anchore/syft), [CycloneDX](https://cyclonedx.org/), [SPDX](https://spdx.dev/) | 3/5; 4/5 при требованиях |
| S11 | Signed release | Release | Подпись артефакта/digest проверяется против доверенной identity/key policy; фиксируется результат верификации. Подписанный Git tag отдельно подтверждает source reference, а не бинарный артефакт | [Cosign](https://docs.sigstore.dev/cosign/verifying/verify/), Sigstore, package signing; signed tags как дополнительное evidence | 4/5 |
| S12 | Build provenance | Release | Attestation проверяемо связывает artifact digest с source revision, builder identity и параметрами сборки; trust policy явно определена. Наличие JSON-файла недостаточно | [SLSA provenance v1.2](https://slsa.dev/spec/v1.2/provenance), verifier и policy evaluator | 4/5 |

### Интерпретация security-проверок

S01 проверяет обнаружение и обработку secrets, S02 — предотвращение push. Встроенные ограничения имён файлов в push rules не равны полноценному сканированию содержимого. Возможности secret push protection зависят от конфигурации и распознаваемых паттернов; обходы нужно учитывать отдельно. [GitLab secret push protection](https://docs.gitlab.com/user/application_security/secret_detection/secret_push_protection/).

При подтверждённой утечке сначала требуется отзыв/ротация секрета и оценка использования. Удаление файла новым commit не удаляет значение из истории. Аудитор не публикует исходное значение секрета в отчёте.

В S06 название расширено относительно краткого «Lockfiles present»: наличие lockfile — только часть воспроизводимого разрешения. `go.sum` содержит checksums модулей и не является самостоятельным lockfile зависимостей; оценивается поведение `go.mod`, module selection и сборки. [Go Modules Reference](https://go.dev/ref/mod#go-sum-files).

Интеграция OpenSSF Scorecard требует проверки поддержки конкретных checks выбранной версией и провайдером. Пропущенная проверка не становится PASS. Встроенные результаты нормализуются по scope и evidence; их числовую шкалу нельзя механически смешивать с баллами других алгоритмов. [OpenSSF Scorecard](https://github.com/ossf/scorecard).

## L. Релизы и воспроизводимость — 6 проверок

| ID | Краткое название | Дополнительные категории | Что проверять и как трактовать | Реализация / evidence | Важность |
| --- | --- | --- | --- | --- | ---: |
| L01 | Reproducible build | Supply chain | Повторные изолированные сборки из одинаковых объявленных inputs дают одинаковые артефакты; если допускается нормализация, её правило и пределы явно описаны | [Reproducible Builds](https://reproducible-builds.org/docs/definition/), сравнение hashes, diffoscope; lockfiles и pinned builders лишь предпосылки | 4/5 |
| L02 | Release traceability | Governance | Production deployment связан с сервисом, environment, commit, pipeline и artifact digest; release tag добавляется, если принят в процессе. Нельзя требовать tag для continuous delivery без tags | [GitLab Deployments API](https://docs.gitlab.com/api/deployments/), environments и registry metadata | 5/5 |
| L03 | Version consistency | Release | В принятой схеме package version, release metadata и tag не противоречат друг другу; для библиотек отдельно проверяется заявленная version policy | [SemVer](https://semver.org/), manifest/tag validator; для commit-based versioning — правило проекта | 3/5 |
| L04 | Release notes | Документация | По релизу доступны значимые изменения, migration notes и breaking changes; auto-generated список commits оценивается на пригодность для потребителя | `CHANGELOG.md`, GitLab Releases, generated release notes + шаблон проекта | 3/5 |
| L05 | Commit convention | Автоматизация | Машиночитаемый формат применяется там, где он нужен release automation; при squash проверяется итоговый MR title/message. Конвенция не является доказательством качества кода | [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), [commitlint](https://commitlint.js.org/) | 2/5 |
| L06 | Release frequency | Поток | Количество/интервал опубликованных релизов за период относительно типа проекта. Tags, package releases и production deployments считаются раздельно | Releases/tags/registry/deployments events, окна 30/90/180 дней по профилю | 4/5 |

### Воспроизводимость и происхождение

L01 проверяет повторяемость результата сборки. S12 проверяет происхождение конкретного артефакта, S11 — доверенную подпись, L02 — связь с фактическим deployment. Ни один из этих результатов не подразумевает автоматически остальные.

Если сборки сравниваются после удаления timestamps или других полей, в отчёте говорится о совпадении по указанному правилу нормализации. Это нельзя без уточнения называть побитовой воспроизводимостью.

## T. Команда и фактический процесс — 14 проверок

| ID | Краткое название | Дополнительные категории | Что проверять и как трактовать | Реализация / evidence | Важность |
| --- | --- | --- | --- | --- | ---: |
| T01 | Maintained repository | Устойчивость | Есть соответствующие lifecycle признаки поддержки: человеческие изменения, releases, ответы и действующий owner. Отсутствие commits — сигнал для проверки, а не автоматическая заброшенность | MR/commit/release events, archive/lifecycle metadata; OpenSSF `Maintained` как эвристический ориентир | 4/5 |
| T02 | Contributor absence factor | Ownership | Минимальное число людей, на которых приходится не менее 50% выбранного вида вклада; единица вклада и окно фиксируются. Низкое значение — риск концентрации | [CHAOSS Contributor Absence Factor](https://www.chaoss.community/kb/metric-contributor-absence-factor/), identity normalization, отдельные расчёты по authors и reviewers | 5/5 |
| T03 | Effective ownership coverage | Устойчивость | Доля активных компонентов с минимум двумя людьми, регулярно участвующими в изменениях/review по принятому определению активности; критичные компоненты показываются отдельно | CODEOWNERS + path-level authors/reviewers за 6–12 месяцев; собственная метрика | 5/5 |
| T04 | Review coverage | Качество | Доля merged MR с подтверждённым человеческим review до merge. Отдельно считать formal approvals, независимость и актуальность ревизии | MR approvals/reviews/discussions events; исторические snapshots при необходимости | 5/5 |
| T05 | Self-merge without independent review | Governance | Среди MR, merged автором, выделяется отсутствие независимого review. Сам факт author = merger не является нарушением; рядом показывается общая доля MR без независимого review | Author/merger identities + review/approval timeline и contributors | 4/5 |
| T06 | Time to first review | Responsiveness | Время от согласованного старта до первого квалифицируемого человеческого review; отдельно показывать MR без ответа и их текущий возраст | MR timestamps, draft/ready events, review/discussion events; собственная операционализация responsiveness | 4/5 |
| T07 | MR cycle time | Поток | Время от открытия MR до merge; p50/p85/p95 и размер выборки. Draft time/ready-to-merge можно показывать отдельной метрикой | `merged_at - created_at`, merged MR cohort, сегментация по сервису/типу/размеру | 5/5 |
| T08 | Stale MR and WIP | Поток | Возраст открытых MR, отсутствие активности, число одновременно активных изменений; различать draft, blocked и ready. Порог зависит от процесса | Open MR snapshot, updated/review events, team/service grouping | 4/5 |
| T09 | Change batch size | Риск, review | Распределение changed lines/files/commits; generated/vendor/lockfile changes показываются отдельно. Большой MR — сигнал сложности review, а не доказательство плохого качества | MR diff statistics, file classification, p50/p85 | 4/5 |
| T10 | Throughput trend | Поток | Число merged MR за неделю и rolling trend; учитывать тип, размер, изменение команды и декомпозиции. Не использовать как персональную норму | Merged MR events, окна 4–8 недель, сегментация | 4/5 |
| T11 | Rework/churn | Качество | Доля ранее изменённых строк, изменённых снова за 14/30 дней; refactoring, renames и генерация могут искажать вывод. Churn не эквивалентен дефектам | Собственный diff/blame analysis с фиксированным способом lineage и cohort | 4/5 |
| T12 | Code hotspots | Поддерживаемость | Компоненты с частыми изменениями, высокой сложностью и концентрацией вклада; использовать как список кандидатов на разбор | Нормализованные churn, complexity, ownership indicators; собственная модель ранжирования | 4/5 |
| T13 | Pipeline reliability | CI/CD | Success/failure/retry rates с выделением test/code/infrastructure causes; first-attempt и eventual success считаются отдельно, cancelled/skipped видны | Jobs/pipelines history, attempts, failure reasons и длительности | 4/5 |
| T14 | Delivery performance | Эксплуатация | Пять DORA-метрик на уровне сервиса: change lead time, deployment frequency, failed deployment recovery time, change fail rate, deployment rework rate. Недостающие составляющие остаются UNKNOWN отдельно | [DORA definitions](https://dora.dev/guides/dora-metrics/), production deployments, artifact → commit mapping, incident/remediation events | 5/5 |

### Операционные определения T-проверок

Следующие правила — предлагаемый контракт измерений lct-git-score. Изменения определения должны менять версию метрики.

| ID | Расчёт и необходимые оговорки |
| --- | --- |
| T02 | Сортировать вклад людей по убыванию; найти минимальное k, чья накопленная доля ≥ 50%. Начальная единица — authored merged MR; review считается отдельной серией. При нулевом вкладе значение `null`. Это выбранный вариант применения CHAOSS |
| T03 | Число активных компонентов с ≥ 2 квалифицируемыми участниками / число активных компонентов. Компонент задаётся каталогом путей, критерий активности — профилем. Размер, окно и минимальное участие показываются в отчёте |
| T04 | MR с qualifying human review до merge / все подходящие merged MR окна. Считать numerator/denominator и число MR с неизвестной историей. Неполная история не считается отсутствием review; полную долю не заявлять |
| T05 | MR, merged автором без независимого review / все подходящие merged MR. Дополнительно: author-merge rate и доля без независимого review среди author-merged MR. Нулевой знаменатель даёт `null` |
| T06 | Базовый старт — `created_at`; первая qualifying review event от независимого человека. Ready-for-review вариант хранится отдельно и требует draft events. Автоматические/system notes исключаются |
| T07 | Cohort: MR, merged в окне; длительность в календарном времени. Незамерженные MR не входят в percentile, но обязательно представлены T08. Работа с draft не меняет базовое определение |
| T09 | Размер фиксируется на итоговом diff перед merge. Неполный/truncated API diff требует другого источника или признака неполноты; не интерпретировать пропуск как ноль |
| T11 | Знаменатель — строки, добавленные/изменённые в исходном cohort, с полным последующим окном наблюдения; numerator — из них повторно изменённые строки. Самые свежие commits без полного окна не включать в итоговую долю |
| T12 | Формула вида `churn × complexity × ownership_risk` допустима только после определения нормализации, диапазонов и поведения при пропусках. Отсутствующий показатель не равен нулевому риску |
| T13 | Считать логические pipelines и job attempts отдельно. Для success rate заранее определить denominator завершённых запусков; отмены, пропуски и запуски в процессе показывать отдельными числами |

### T14: delivery-метрики

Определения в таблице следуют [DORA](https://dora.dev/guides/dora-metrics/); детали привязки событий должны быть зафиксированы в адаптере источника.

| Метрика | Что измеряется | Нужные данные |
| --- | --- | --- |
| Change lead time | Время от commit изменения до его появления в production | Сопоставление source commits с фактическим production artifact и временем deployment |
| Deployment frequency | Число production deployments за период либо интервал между ними | Уникальные deployment events с service/environment |
| Failed deployment recovery time | Время восстановления после неудачного deployment, потребовавшего вмешательства | Связанный неудачный deployment и событие восстановления |
| Change fail rate | Доля deployments, потребовавших немедленного исправления, например rollback/hotfix | Все подходящие deployments и их признак failure/intervention |
| Deployment rework rate | Доля незапланированных deployments вследствие production incident | Deployment events, плановый/внеплановый статус и связи с incidents |

Несколько incidents у одного deployment не должны несколько раз увеличивать numerator change fail rate. Неудачный deployment может быть исправлен rollback без нового commit, поэтому Git log не заменяет operational events. Отсутствие incidents подтверждает ноль failures только при достаточной полноте их регистрации; иначе это UNKNOWN. Нулевое число deployments означает неопределённые rates, а не идеальную стабильность.

## Правила применения ко всему каталогу

1. **Проверять факт выполнения.** Файл конфигурации, badge, название job и назначенный reviewer — слабее результата исполнения и событий до merge.
2. **Сохранять область анализа.** Указать service/path, revision, branches, environments, окно и полноту refs/API pages.
3. **Отделять недостаток данных.** Permission denied, expired artifacts, missing history и unsupported adapters имеют явные reason codes.
4. **Не скрывать исключения.** Accepted risk сохраняется рядом с исходной находкой, имеет владельца и срок; не даёт автоматический PASS.
5. **Не применять общий порог к несопоставимым проектам.** Coverage, frequency, размер MR и время review зависят от контекста.
6. **Сохранять направление улучшения.** Для ownership полезна устойчивость, для CI — быстрый надёжный feedback; оптимизация одного числа не должна создавать противоположный риск.
7. **Давать действие.** Находка должна указывать конкретный scope и следующий шаг: назначить owner, ограничить push, исправить обязательную job, отозвать secret или восстановить источник данных.

## Приоритет реализации

Рекомендуемый MVP и правила scoring приведены в [методологии](repository-health-approach.md#13-порядок-внедрения). Каталог намеренно шире первого выпуска: история flaky tests, path-level ownership, provenance и DORA требуют источников и накопления данных, которых может не быть при первом подключении репозитория.

Первые кандидаты на нормативные gates — подтверждаемые контроли G01–G07 и выбранные security-проверки по профилю. R03, R06, Q09, Q10, L06 и большинство T-метрик сначала используются как наблюдения. Решение о блокировке принимается отдельной политикой, а не автоматически по важности 5/5.
