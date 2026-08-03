#!/usr/bin/env bash
# Moodle 应用层配置（Spec §11.4 / WP3 第一阶段）—— infra/moodle.sh 只建 VM 骨架，
# 这个脚本负责骨架之上的一切：起容器、装库、开 Web Services、造课程与合成学生。
#
#   bash infra/moodle_provision.sh                # 只打印会做什么，不改动任何东西
#   bash infra/moodle_provision.sh --apply         # 真正执行
#
# 幂等：可以在同一台已部分配置的 VM 上重复跑，也可以在全新 VM 上从零跑通。
# 每一步先探测"是否已完成"，已完成就跳过，不会重复造课程/学生或覆盖已知密码。
#
# 密钥纪律：admin 密码与 Web Services token 只经过"VM 上的临时文件（root-only）
# → gcloud compute scp 到本机零时目录 → gcloud secrets versions add → 立即删除
# 两端的明文副本"这条路径。脚本任何地方都不 echo/print 密钥内容；curl 验证时
# token 直接在 VM 内从 Secret Manager 读取并使用，从不回传到本机终端。
#
# 前置：VM 必须已由 infra/moodle.sh create 建好，且开机脚本跑完出现 /opt/moodle/READY
# （clone 了 moodle-docker，装好了 docker）。这个脚本不建 VM、不开防火墙。

set -euo pipefail
cd "$(dirname "$0")/.."
source infra/config.sh

parse_common_flags "$@"

SSH_TARGET="$MOODLE_INSTANCE"
SSH_ARGS=(compute ssh "$SSH_TARGET" --zone="$MOODLE_ZONE" --project="$PROJECT_ID" --quiet)
SCP_ARGS=(compute scp --zone="$MOODLE_ZONE" --project="$PROJECT_ID" --quiet)

MOODLE_DOCKER_DB="mariadb"
MOODLE_DOCKER_WEB_PORT="8080"
MOODLE_BRANCH="MOODLE_405_STABLE"
REMOTE_WWWROOT="/opt/moodle/moodle"
REMOTE_DOCKER_DIR="/opt/moodle/moodle-docker"
ADMIN_SECRET_NAME="campuspath-moodle-admin-password"
TOKEN_SECRET_NAME="campuspath-moodle-ws-token"   # 已在 infra/config.sh 的 REQUIRED_SECRETS 里

# 9 门课程骨架 + 对应学生名单（与 seed/generated/full/student_course_records.json
# 里 STU-A..STU-L 真实修读的课程对齐，方便日后跟 SIS 合成数据交叉验证）。
COURSE_SHORTNAMES=(COMP1021 COMP1023 ENTR1001 HUMA1000 HUMA1001 HUMA1009 HUMA1010 COMP1001 COMP1028)
COURSE_FULLNAMES=("COMP 1021" "COMP 1023" "ENTR 1001" "HUMA 1000" "HUMA 1001" "HUMA 1009" "HUMA 1010" "COMP 1001" "COMP 1028")

# ── 远程执行辅助 ────────────────────────────────────────────────────
# remote <desc> <shell-snippet>：在 VM 上以 sudo bash -c 执行，DRY_RUN 下只打印。
remote() {
  local desc="$1"; local snippet="$2"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf "  ${DIM}[dry-run]${NC} ssh %s: %s\n" "$desc" "$(echo "$snippet" | head -1)…"
    return 0
  fi
  printf "  ${DIM}\$ ssh${NC} %s\n" "$desc"
  gcloud "${SSH_ARGS[@]}" -- "sudo bash -c $(printf '%q' "$snippet")"
}

# push_php <local-tmp-file> <remote-admin-cli-filename>：把本机生成的 php 助手
# 脚本传到 VM 的 admin/cli/ 下（该目录只是普通 CLI 脚本堆放处，不受插件目录扫描
# 约束，且不属于本仓库——纯 VM 侧工件）。
push_php() {
  local localfile="$1"; local remotename="$2"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf "  ${DIM}[dry-run]${NC} scp %s -> %s/admin/cli/%s\n" "$localfile" "$REMOTE_WWWROOT" "$remotename"
    return 0
  fi
  gcloud "${SCP_ARGS[@]}" "$localfile" "$SSH_TARGET:~/${remotename}"
  remote "install $remotename" "mv /home/\$(logname)/${remotename} ${REMOTE_WWWROOT}/admin/cli/${remotename} && chown root:root ${REMOTE_WWWROOT}/admin/cli/${remotename}"
}

# dc <args...>：在 REMOTE_DOCKER_DIR 里以正确的环境变量跑 bin/moodle-docker-compose。
dc_prefix() {
  echo "export MOODLE_DOCKER_WWWROOT=${REMOTE_WWWROOT} MOODLE_DOCKER_DB=${MOODLE_DOCKER_DB} MOODLE_DOCKER_WEB_PORT=${MOODLE_DOCKER_WEB_PORT}; cd ${REMOTE_DOCKER_DIR};"
}

banner
step "0. 前置检查：/opt/moodle/READY"
if [ "$DRY_RUN" -eq 0 ]; then
  if ! gcloud "${SSH_ARGS[@]}" -- 'test -f /opt/moodle/READY' >/dev/null 2>&1; then
    bad "/opt/moodle/READY 不存在——开机脚本还没跑完，或者 VM 还没建。先跑 infra/moodle.sh create --apply 并等待。"
    exit 1
  fi
  ok "READY 存在"
else
  warn "dry-run，跳过 READY 探测"
fi

step "1. Moodle 源码 (${MOODLE_BRANCH})"
remote "clone moodle source" "
  mkdir -p ${REMOTE_WWWROOT}
  if [ ! -f ${REMOTE_WWWROOT}/version.php ]; then
    git clone --depth 1 --branch ${MOODLE_BRANCH} https://github.com/moodle/moodle.git ${REMOTE_WWWROOT}
  else
    echo 'moodle source already present'
  fi
"

step "2. config.php + docker compose up"
remote "config.php + compose up" "
  cp ${REMOTE_DOCKER_DIR}/config.docker-template.php ${REMOTE_WWWROOT}/config.php
  $(dc_prefix)
  bin/moodle-docker-compose up -d
  bin/moodle-docker-wait-for-db
"

step "3. 数据库安装（幂等：已装过就跳过，不覆盖已知密码）"

TMPDIR_LOCAL=$(mktemp -d)
trap 'rm -rf "$TMPDIR_LOCAL"' EXIT

cat > "$TMPDIR_LOCAL/campuspath_probe_installed.php" <<'PHP_EOF'
<?php
// 探测 Moodle 是否已完成安装（mdl_config 表存在即视为已装）。
define('CLI_SCRIPT', true);
require(__DIR__ . '/../../config.php');
global $DB;
$installed = false;
try {
    $installed = $DB->get_manager()->table_exists('config');
} catch (\Throwable $e) {
    $installed = false;
}
echo $installed ? "INSTALLED\n" : "NOT_INSTALLED\n";
PHP_EOF
push_php "$TMPDIR_LOCAL/campuspath_probe_installed.php" "campuspath_probe_installed.php"

INSTALLED_STATE="unknown"
if [ "$DRY_RUN" -eq 0 ]; then
  INSTALLED_STATE=$(gcloud "${SSH_ARGS[@]}" -- "sudo bash -c '$(dc_prefix) bin/moodle-docker-compose exec -T webserver php admin/cli/campuspath_probe_installed.php'" 2>/dev/null | tail -1 | tr -d '\r')
fi

if [ "$INSTALLED_STATE" = "INSTALLED" ]; then
  ok "数据库已安装，跳过 install_database.php（admin 密码沿用 Secret Manager 里已有的版本）"
else
  warn "数据库未安装，将生成随机 admin 密码并安装（密码只进 Secret Manager，不打印）"
  remote "generate admin password + install_database.php" "
    set -euo pipefail
    mkdir -p /root/.campuspath_secrets
    chmod 700 /root/.campuspath_secrets
    openssl rand -base64 24 > /root/.campuspath_secrets/admin_pass
    chmod 600 /root/.campuspath_secrets/admin_pass
    $(dc_prefix)
    ADMINPASS=\"\$(cat /root/.campuspath_secrets/admin_pass)\"
    bin/moodle-docker-compose exec -T webserver php admin/cli/install_database.php \
      --agree-license \
      --fullname='CampusPath Moodle (Synthetic)' \
      --shortname='campuspath_moodle' \
      --summary='CampusPath synthetic Moodle instance for WP3' \
      --adminuser=admin \
      --adminpass=\"\$ADMINPASS\" \
      --adminemail=admin@campuspath.invalid < /dev/null
  "
  if [ "$DRY_RUN" -eq 0 ]; then
    remote "stage admin pass for scp" "
      cp /root/.campuspath_secrets/admin_pass /home/\$(logname)/.moodle_admin_pass_xfer
      chown \$(logname):\$(logname) /home/\$(logname)/.moodle_admin_pass_xfer
      chmod 600 /home/\$(logname)/.moodle_admin_pass_xfer
    "
    gcloud "${SCP_ARGS[@]}" "$SSH_TARGET:~/.moodle_admin_pass_xfer" "$TMPDIR_LOCAL/admin_pass"
    if ! gcloud secrets describe "$ADMIN_SECRET_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
      gcloud secrets create "$ADMIN_SECRET_NAME" --project="$PROJECT_ID" \
        --replication-policy=user-managed --locations="$APP_REGION" >/dev/null
    fi
    gcloud secrets versions add "$ADMIN_SECRET_NAME" --project="$PROJECT_ID" \
      --data-file="$TMPDIR_LOCAL/admin_pass" >/dev/null
    rm -f "$TMPDIR_LOCAL/admin_pass"
    remote "wipe admin pass staging copies" "
      rm -f /home/\$(logname)/.moodle_admin_pass_xfer
      rm -f /root/.campuspath_secrets/admin_pass
    "
    ok "admin 密码已写入 Secret Manager: ${ADMIN_SECRET_NAME}（明文两端均已清除）"
  fi
fi

step "4. Web Services + REST 协议"
remote "enable webservices + rest" "
  $(dc_prefix)
  bin/moodle-docker-compose exec -T webserver php admin/cli/cfg.php --name=enablewebservices --set=1
  bin/moodle-docker-compose exec -T webserver php admin/cli/cfg.php --name=webserviceprotocols --set=rest
"

step "5. 专用 service 账号 + token（幂等：已存在就复用）"
cat > "$TMPDIR_LOCAL/campuspath_ws_setup.php" <<'PHP_EOF'
<?php
// 创建/复用专用 external service + 服务账号 + 永久 REST token。
// 幂等：每张表插入前先查是否已存在。token 写到 root-only 文件，从不 echo。
define('CLI_SCRIPT', true);
require(__DIR__ . '/../../config.php');
require_once($CFG->dirroot . '/webservice/lib.php');
require_once($CFG->dirroot . '/user/lib.php');
require_once($CFG->dirroot . '/lib/externallib.php');
require_once($CFG->dirroot . '/lib/accesslib.php');

global $DB, $CFG;

$shortname = 'campuspath_api';
$servicename = 'CampusPath Integration API';
$svcusername = 'campuspath_svc';
$tokenoutfile = '/root/.campuspath_secrets/ws_token';

$functions = [
    'core_webservice_get_site_info',
    'core_course_get_courses',
    'core_course_get_courses_by_field',
    'core_course_get_contents',
    'core_enrol_get_enrolled_users',
    'core_enrol_get_users_courses',
    'core_user_get_users',
    'core_user_get_users_by_field',
    'enrol_manual_enrol_users',
];

$service = $DB->get_record('external_services', ['shortname' => $shortname]);
if (!$service) {
    $obj = new stdClass();
    $obj->name = $servicename;
    $obj->shortname = $shortname;
    $obj->enabled = 1;
    $obj->restrictedusers = 1;
    $obj->downloadfiles = 0;
    $obj->uploadfiles = 0;
    $obj->timecreated = time();
    $obj->timemodified = time();
    $id = $DB->insert_record('external_services', $obj);
    $service = $DB->get_record('external_services', ['id' => $id]);
    fwrite(STDOUT, "CREATED_SERVICE id={$service->id}\n");
} else {
    if (!$service->enabled) {
        $service->enabled = 1;
        $service->restrictedusers = 1;
        $DB->update_record('external_services', $service);
    }
    fwrite(STDOUT, "SERVICE_EXISTS id={$service->id}\n");
}

foreach ($functions as $f) {
    if (!$DB->record_exists('external_services_functions', ['externalserviceid' => $service->id, 'functionname' => $f])) {
        $DB->insert_record('external_services_functions', (object) [
            'externalserviceid' => $service->id,
            'functionname' => $f,
        ]);
        fwrite(STDOUT, "  +function $f\n");
    }
}

$user = $DB->get_record('user', ['username' => $svcusername, 'mnethostid' => $CFG->mnet_localhost_id, 'deleted' => 0]);
if (!$user) {
    $randpass = base64_encode(random_bytes(24));
    $newuser = new stdClass();
    $newuser->username = $svcusername;
    $newuser->password = $randpass;
    $newuser->firstname = 'CampusPath';
    $newuser->lastname = 'Service Account';
    $newuser->email = 'campuspath-svc@campuspath.invalid';
    $newuser->auth = 'manual';
    $newuser->confirmed = 1;
    $newuser->mnethostid = $CFG->mnet_localhost_id;
    $newuser->policyagreed = 1;
    $userid = user_create_user($newuser, false, false);
    unset($randpass);
    $user = $DB->get_record('user', ['id' => $userid]);
    fwrite(STDOUT, "CREATED_SVC_USER id={$user->id}\n");
} else {
    fwrite(STDOUT, "SVC_USER_EXISTS id={$user->id}\n");
}

$context = context_system::instance();
$roleid = $DB->get_field('role', 'id', ['shortname' => 'manager']);
if ($roleid) {
    $hasrole = $DB->record_exists('role_assignments', ['roleid' => $roleid, 'contextid' => $context->id, 'userid' => $user->id]);
    if (!$hasrole) {
        role_assign($roleid, $user->id, $context->id);
        fwrite(STDOUT, "ROLE_ASSIGNED manager\n");
    } else {
        fwrite(STDOUT, "ROLE_ALREADY_ASSIGNED manager\n");
    }
} else {
    fwrite(STDERR, "WARNING: manager role not found, capability checks may fail\n");
}

// Stock Manager archetype 不含 webservice/rest:use，得手动补，否则 REST 调用
// 全部 403（Access control exception）。
assign_capability('webservice/rest:use', CAP_ALLOW, $roleid, $context->id, true);
accesslib_clear_all_caches(false);
fwrite(STDOUT, "GRANTED webservice/rest:use\n");

if (!$DB->record_exists('external_services_users', ['externalserviceid' => $service->id, 'userid' => $user->id])) {
    $DB->insert_record('external_services_users', (object) [
        'externalserviceid' => $service->id,
        'userid' => $user->id,
    ]);
    fwrite(STDOUT, "SERVICE_USER_LINKED\n");
} else {
    fwrite(STDOUT, "SERVICE_USER_ALREADY_LINKED\n");
}

$existing = $DB->get_record('external_tokens', [
    'userid' => $user->id,
    'externalserviceid' => $service->id,
    'tokentype' => EXTERNAL_TOKEN_PERMANENT,
]);
if ($existing) {
    $token = $existing->token;
    fwrite(STDOUT, "TOKEN_EXISTS\n");
} else {
    $token = external_generate_token(EXTERNAL_TOKEN_PERMANENT, $service, $user->id, $context, 0, '');
    fwrite(STDOUT, "TOKEN_CREATED\n");
}

if (!is_dir('/root/.campuspath_secrets')) {
    mkdir('/root/.campuspath_secrets', 0700, true);
}
file_put_contents($tokenoutfile, $token);
chmod($tokenoutfile, 0600);
fwrite(STDOUT, "TOKEN_WRITTEN_TO_FILE $tokenoutfile\n");
PHP_EOF
push_php "$TMPDIR_LOCAL/campuspath_ws_setup.php" "campuspath_ws_setup.php"
remote "run campuspath_ws_setup.php" "$(dc_prefix) bin/moodle-docker-compose exec -T webserver php admin/cli/campuspath_ws_setup.php"

if [ "$DRY_RUN" -eq 0 ]; then
  step "5b. token -> Secret Manager"
  # token 是 PHP 脚本在容器内部写的，容器文件系统跟宿主机是分开的——
  # 必须先 docker cp 到宿主机，才能再 scp 下山。全程不落到本机以外的地方，
  # 也从不经过 stdout。
  WEBSERVER_CID=$(gcloud "${SSH_ARGS[@]}" -- "sudo bash -c '$(dc_prefix) bin/moodle-docker-compose ps -q webserver'" 2>/dev/null | tail -1 | tr -d '\r')
  remote "docker cp token out to host" "
    mkdir -p /root/.campuspath_secrets && chmod 700 /root/.campuspath_secrets
    docker cp ${WEBSERVER_CID}:/root/.campuspath_secrets/ws_token /root/.campuspath_secrets/ws_token
    chmod 600 /root/.campuspath_secrets/ws_token
    cp /root/.campuspath_secrets/ws_token /home/\$(logname)/.moodle_ws_token_xfer
    chown \$(logname):\$(logname) /home/\$(logname)/.moodle_ws_token_xfer
    chmod 600 /home/\$(logname)/.moodle_ws_token_xfer
  "
  gcloud "${SCP_ARGS[@]}" "$SSH_TARGET:~/.moodle_ws_token_xfer" "$TMPDIR_LOCAL/ws_token"
  if ! gcloud secrets describe "$TOKEN_SECRET_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$TOKEN_SECRET_NAME" --project="$PROJECT_ID" \
      --replication-policy=user-managed --locations="$APP_REGION" >/dev/null
  fi
  gcloud secrets versions add "$TOKEN_SECRET_NAME" --project="$PROJECT_ID" \
    --data-file="$TMPDIR_LOCAL/ws_token" >/dev/null
  rm -f "$TMPDIR_LOCAL/ws_token"
  remote "wipe token staging copies" "
    rm -f /home/\$(logname)/.moodle_ws_token_xfer
    docker exec ${WEBSERVER_CID} rm -rf /root/.campuspath_secrets
    rm -rf /root/.campuspath_secrets
  "
  ok "token 已写入 Secret Manager: ${TOKEN_SECRET_NAME}（明文各端均已清除）"
fi

step "6. 课程骨架（tool_generator，8-10 门）"
cat > "$TMPDIR_LOCAL/campuspath_probe_course.php" <<'PHP_EOF'
<?php
define('CLI_SCRIPT', true);
require(__DIR__ . '/../../config.php');
global $DB;
$sn = $argv[1] ?? '';
echo $DB->record_exists('course', ['shortname' => $sn]) ? "1" : "0";
PHP_EOF
push_php "$TMPDIR_LOCAL/campuspath_probe_course.php" "campuspath_probe_course.php"

if [ "$DRY_RUN" -eq 0 ]; then
  for i in "${!COURSE_SHORTNAMES[@]}"; do
    sn="${COURSE_SHORTNAMES[$i]}"
    fn="${COURSE_FULLNAMES[$i]}"
    exists=$(gcloud "${SSH_ARGS[@]}" -- "sudo bash -c '$(dc_prefix) bin/moodle-docker-compose exec -T webserver php admin/cli/campuspath_probe_course.php ${sn}'" 2>/dev/null | tail -1 | tr -d '\r')
    if [ "$exists" = "1" ]; then
      ok "course $sn 已存在，跳过"
    else
      warn "生成 course $sn ($fn)"
      remote "maketestcourse $sn" "
        $(dc_prefix)
        bin/moodle-docker-compose exec -T webserver php admin/tool/generator/cli/maketestcourse.php \
          --shortname=${sn} --fullname='${fn} (Synthetic / Demo Data)' \
          --summary='CampusPath synthetic course - ${fn}' --size=S --quiet
      "
    fi
  done
else
  warn "dry-run，跳过课程存在性探测（会创建：${COURSE_SHORTNAMES[*]}）"
fi

step "7. 12 个合成学生 (stu-a..stu-l) + 按 seed 名单选课"
cat > "$TMPDIR_LOCAL/campuspath_seed_students.php" <<'PHP_EOF'
<?php
// 12 个合成学生账号 + 按 seed/generated/full/student_course_records.json 的
// 修读名单选课。幂等：用户/选课都先查是否存在。
define('CLI_SCRIPT', true);
require(__DIR__ . '/../../config.php');
require_once($CFG->dirroot . '/user/lib.php');
require_once($CFG->dirroot . '/enrol/manual/locallib.php');

global $DB, $CFG;

$letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'];

$roster = [
    'COMP1021' => ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'],
    'COMP1023' => ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'],
    'ENTR1001' => ['A', 'B', 'C', 'E', 'F', 'H', 'K', 'L'],
    'HUMA1000' => ['A', 'B', 'C', 'E', 'F', 'H', 'K', 'L'],
    'HUMA1001' => ['A', 'B', 'C', 'E', 'F', 'H', 'K', 'L'],
    'HUMA1009' => ['A', 'B', 'C', 'E', 'F', 'H', 'K', 'L'],
    'HUMA1010' => ['A', 'B', 'C', 'E', 'F', 'H', 'K', 'L'],
    'COMP1001' => ['B', 'C', 'G', 'H', 'I', 'J', 'K', 'L'],
    'COMP1028' => ['B', 'C', 'G', 'H', 'I', 'J', 'K', 'L'],
];

$userids = [];
foreach ($letters as $l) {
    $username = 'stu-' . strtolower($l);
    $user = $DB->get_record('user', ['username' => $username, 'mnethostid' => $CFG->mnet_localhost_id, 'deleted' => 0]);
    if (!$user) {
        $randpass = base64_encode(random_bytes(24));
        $newuser = new stdClass();
        $newuser->username = $username;
        $newuser->password = $randpass;
        $newuser->firstname = 'Synthetic';
        $newuser->lastname = 'Student ' . $l;
        $newuser->email = $username . '@campuspath.invalid';
        $newuser->auth = 'manual';
        $newuser->confirmed = 1;
        $newuser->mnethostid = $CFG->mnet_localhost_id;
        $newuser->policyagreed = 1;
        $uid = user_create_user($newuser, false, false);
        unset($randpass);
        echo "CREATED_USER $username id=$uid\n";
        $userids[$l] = $uid;
    } else {
        echo "USER_EXISTS $username id={$user->id}\n";
        $userids[$l] = $user->id;
    }
}

$studentroleid = $DB->get_field('role', 'id', ['shortname' => 'student']);
if (!$studentroleid) {
    fwrite(STDERR, "FATAL: student role not found\n");
    exit(1);
}

$manual = enrol_get_plugin('manual');

foreach ($roster as $shortname => $students) {
    $course = $DB->get_record('course', ['shortname' => $shortname]);
    if (!$course) {
        fwrite(STDERR, "WARNING: course $shortname not found, skipping enrolments\n");
        continue;
    }
    $instance = $DB->get_record('enrol', ['courseid' => $course->id, 'enrol' => 'manual']);
    if (!$instance) {
        $instanceid = $manual->add_instance($course);
        $instance = $DB->get_record('enrol', ['id' => $instanceid]);
        echo "CREATED_ENROL_INSTANCE $shortname\n";
    }
    foreach ($students as $l) {
        $uid = $userids[$l];
        $already = $DB->record_exists('user_enrolments', ['enrolid' => $instance->id, 'userid' => $uid]);
        if ($already) {
            continue;
        }
        $manual->enrol_user($instance, $uid, $studentroleid);
        echo "ENROLLED stu-" . strtolower($l) . " -> $shortname\n";
    }
}

echo "DONE\n";
PHP_EOF
push_php "$TMPDIR_LOCAL/campuspath_seed_students.php" "campuspath_seed_students.php"
remote "run campuspath_seed_students.php" "$(dc_prefix) bin/moodle-docker-compose exec -T webserver php admin/cli/campuspath_seed_students.php"

step "8. 验证（token 全程留在 VM 内，从 Secret Manager 读，从不回传本机）"
if [ "$DRY_RUN" -eq 0 ]; then
  gcloud "${SSH_ARGS[@]}" -- '
set -e
TOKEN=$(gcloud secrets versions access latest --secret='"$TOKEN_SECRET_NAME"' --project='"$PROJECT_ID"')
BASE="http://localhost:'"$MOODLE_DOCKER_WEB_PORT"'/webservice/rest/server.php"

echo "-- site info --"
curl -s "$BASE?wstoken=$TOKEN&wsfunction=core_webservice_get_site_info&moodlewsrestformat=json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(\"sitename:\", d.get(\"sitename\")); print(\"release:\", d.get(\"release\")); print(\"num_functions:\", len(d.get(\"functions\",[])))"

echo "-- course count --"
curl -s "$BASE?wstoken=$TOKEN&wsfunction=core_course_get_courses&moodlewsrestformat=json" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
courses=[c for c in d if c[\"id\"]!=1]
print(\"course_count:\", len(courses))
print(sorted(c[\"shortname\"] for c in courses))
assert len(courses) >= 8, \"expected >=8 courses\"
"

echo "-- stu-* users --"
curl -s -G "$BASE" \
  --data-urlencode "wstoken=$TOKEN" \
  --data-urlencode "wsfunction=core_user_get_users" \
  --data-urlencode "moodlewsrestformat=json" \
  --data-urlencode "criteria[0][key]=email" \
  --data-urlencode "criteria[0][value]=%campuspath.invalid" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
us=[u[\"username\"] for u in d[\"users\"]]
stus=[u for u in us if u.startswith(\"stu-\")]
print(\"stu_count:\", len(stus))
assert len(stus) == 12, \"expected 12 stu-* accounts\"
"
unset TOKEN
echo "ALL VERIFICATION CHECKS PASSED"
'
else
  warn "dry-run，跳过验证"
fi

step "完成"
ok "Moodle: http://localhost:${MOODLE_DOCKER_WEB_PORT}/ （只能通过 ssh -L 端口转发访问，不开公网）"
ok "  gcloud compute ssh ${MOODLE_INSTANCE} --zone=${MOODLE_ZONE} --project=${PROJECT_ID} -- -L ${MOODLE_DOCKER_WEB_PORT}:localhost:${MOODLE_DOCKER_WEB_PORT}"
ok "admin 密码：Secret Manager -> ${ADMIN_SECRET_NAME}"
ok "Web Services token：Secret Manager -> ${TOKEN_SECRET_NAME}"
