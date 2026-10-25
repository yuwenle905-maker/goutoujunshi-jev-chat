#import "GT.h"
extern NSString *GTLogText(void);
extern void GTClearLogs(void);

@interface GTEditor : UIViewController
@property UITextView *textView;
@property NSString *initial;
@property (copy) void (^commit)(NSString *);
@end
@implementation GTEditor
- (void)viewDidLoad {
    [super viewDidLoad]; self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.textView = [[UITextView alloc] initWithFrame:self.view.bounds]; self.textView.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    self.textView.font = [UIFont systemFontOfSize:17]; self.textView.text = self.initial; self.textView.textContainerInset = UIEdgeInsetsMake(20, 16, 30, 16); [self.view addSubview:self.textView];
    self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:@"保存" style:UIBarButtonItemStyleDone target:self action:@selector(save)];
}
- (void)save { if (self.commit) self.commit(self.textView.text); [self.navigationController popViewControllerAnimated:YES]; }
@end

@implementation GTSettings
- (instancetype)init { return [super initWithStyle:UITableViewStyleInsetGrouped]; }
- (NSArray *)rows {
    if (self.scope) return @[@[@"此对象启用", @"enabled", @"switch"], @[@"独立人设（留空继承）", @"persona", @"text"], @[@"关系阶段", @"stage", @"text"], @[@"关系目标", @"goal", @"text"], @[@"当前状态", @"state", @"text"], @[@"背景与边界", @"boundaries", @"text"], @[@"人工样本 JSON", @"examples", @"json"], @[@"核对后解除发送熔断", @"unpause", @"action"]];
    return @[@[@"启用 AI 聊天", @"enabled", @"switch"], @[@"同意当前会话上传云端与 DeepSeek", @"cloud_consent", @"switch"], @[@"自动发送 · 弹窗5秒确认", @"automatic", @"switch"], @[@"对所有好友启用（默认关闭）", @"all_friends", @"switch"], @[@"启用群聊", @"groups", @"switch"], @[@"群聊免 @（明确开启才处理）", @"group_without_at", @"switch"], @[@"后端 HTTPS 地址", @"endpoint", @"short"], @[@"设备令牌", @"device_token", @"secret"], @[@"DeepSeek Key（可选，覆盖服务器 Key）", @"deepseek_key", @"secret"], @[@"模型", @"model", @"short"], @[@"获取模型列表", @"models", @"action"], @[@"Temperature · 0至2", @"temperature", @"number"], @[@"全局人设", @"persona", @"text"], @[@"网络表达素材（非实时）", @"meme_bank", @"text"], @[@"自定义前缀", @"prefix", @"short"], @[@"自定义后缀", @"suffix", @"short"]];
}
- (NSMutableDictionary *)store { return self.scope ? [GTConfig.shared profile:self.scope] : GTConfig.shared.values; }
- (void)viewDidLoad { [super viewDidLoad]; self.title = self.scope ? @"此段关系 · 独立配置" : @"AI 助手"; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return self.rows.count; }
- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
    return self.scope ? @"只影响当前账号下的此对象。修改样本仅学习表达，不训练模型权重。历史全文只在内存保留最近40条；重启不自动读取旧数据库。" : @"密钥和令牌存 Keychain。云端会收到当前对象近期上下文和配置；可选 Key 只发给你配置的服务器，请确认服务器可信。默认人工审核。微信8.0.75发送适配尚待真机验证，当前构建不开放实发。固定15秒间隔、每日50条保护，不保证防封。";
}
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    NSArray *row = self.rows[indexPath.row]; UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    cell.textLabel.text = row[0]; cell.textLabel.numberOfLines = 0;
    if ([row[2] isEqual:@"switch"]) { UISwitch *s = [UISwitch new]; s.tag = indexPath.row; s.on = [self.store[row[1]] boolValue]; [s addTarget:self action:@selector(toggle:) forControlEvents:UIControlEventValueChanged]; cell.accessoryView = s; }
    else { cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator; cell.detailTextLabel.text = [row[2] isEqual:@"secret"] ? (GTSecret(row[1]).length ? @"已配置" : @"未配置") : [self.store[row[1]] description]; cell.detailTextLabel.numberOfLines = 2; }
    return cell;
}
- (void)toggle:(UISwitch *)sender {
    NSArray *row = self.rows[sender.tag]; self.store[row[1]] = @(sender.on); [GTConfig.shared save];
    if ([row[1] isEqual:@"enabled"] && !sender.on) { for (NSString *scope in GTCoordinator.shared.revisions.allKeys) GTCoordinator.shared.revisions[scope] = @([GTCoordinator.shared.revisions[scope] integerValue] + 1); [GTCoordinator.shared.drafts removeAllObjects]; }
    GTLog(@"settings_changed");
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES]; NSArray *row = self.rows[indexPath.row]; NSString *key = row[1], *kind = row[2];
    if ([kind isEqual:@"switch"]) return;
    if ([key isEqual:@"models"]) { [[GTClient shared] request:@"/v1/models" body:nil completion:^(NSDictionary *result, NSString *error) {
        if (error) { GTLog(error); return; } UIAlertController *menu = [UIAlertController alertControllerWithTitle:@"选择模型" message:nil preferredStyle:UIAlertControllerStyleAlert];
        for (id model in result[@"models"]) if ([model isKindOfClass:NSString.class]) [menu addAction:[UIAlertAction actionWithTitle:model style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a) { self.store[@"model"] = model; [GTConfig.shared save]; [self.tableView reloadData]; }]];
        [menu addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]]; [self presentViewController:menu animated:YES completion:nil];
    }]; return; }
    if ([key isEqual:@"unpause"]) {
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"已核对微信实际发送结果？" message:@"解除此对象熔断只允许后续新消息继续，不重发旧消息。" preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
        [alert addAction:[UIAlertAction actionWithTitle:@"已核对，恢复后续消息" style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a) { [GTCoordinator.shared.paused removeObject:self.scope]; [GTConfig.shared.values[@"blocked"] removeObjectForKey:self.scope]; [GTConfig.shared save]; GTLog(@"peer_resumed_after_review"); }]];
        [self presentViewController:alert animated:YES completion:nil]; return;
    }
    if ([kind isEqual:@"text"] || [kind isEqual:@"json"]) {
        GTEditor *editor = [GTEditor new]; editor.title = row[0];
        editor.initial = [kind isEqual:@"json"] ? [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:self.store[key] ?: @[] options:NSJSONWritingPrettyPrinted error:nil] encoding:NSUTF8StringEncoding] : self.store[key];
        editor.commit = ^(NSString *value) {
            if (value.length > 12000) { GTLog(@"preset_too_large"); return; }
            if ([kind isEqual:@"json"]) {
                id array = [NSJSONSerialization JSONObjectWithData:[value dataUsingEncoding:NSUTF8StringEncoding] options:NSJSONReadingMutableContainers error:nil];
                if (![array isKindOfClass:NSArray.class] || [array count] > 6) { GTLog(@"invalid_examples_json"); return; }
                for (id x in array) if (![x isKindOfClass:NSDictionary.class] || ![x[@"incoming"] isKindOfClass:NSString.class] || ![x[@"edited"] isKindOfClass:NSString.class]) { GTLog(@"invalid_example_fields"); return; }
                self.store[key] = array;
            } else self.store[key] = value;
            [GTConfig.shared save]; [self.tableView reloadData];
        }; [self.navigationController pushViewController:editor animated:YES]; return;
    }
    UIAlertController *edit = [UIAlertController alertControllerWithTitle:row[0] message:[kind isEqual:@"secret"] ? @"留空并保存会删除此项" : nil preferredStyle:UIAlertControllerStyleAlert];
    [edit addTextFieldWithConfigurationHandler:^(UITextField *f) { f.secureTextEntry = [kind isEqual:@"secret"]; f.autocapitalizationType = UITextAutocapitalizationTypeNone; f.autocorrectionType = UITextAutocorrectionTypeNo; f.text = [kind isEqual:@"secret"] ? GTSecret(key) : [self.store[key] description]; }];
    [edit addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    [edit addAction:[UIAlertAction actionWithTitle:@"保存" style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a) {
        NSString *value = edit.textFields.firstObject.text ?: @"";
        if ([kind isEqual:@"secret"]) { if (!GTSaveSecret(key, value)) GTLog(@"keychain_write_failed"); }
        else if ([kind isEqual:@"number"]) { NSScanner *scanner = [NSScanner scannerWithString:value]; double n; if (![scanner scanDouble:&n] || !scanner.isAtEnd || !isfinite(n) || n < 0 || n > 2) { GTLog(@"invalid_temperature"); return; } self.store[key] = @(n); }
        else self.store[key] = value;
        [GTConfig.shared save]; [self.tableView reloadData];
    }]]; [self presentViewController:edit animated:YES completion:nil];
}
@end

@implementation GTHome
- (void)viewDidLoad {
    [super viewDidLoad]; self.title = @"狗头 AI"; self.view.backgroundColor = UIColor.systemGroupedBackgroundColor;
    self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(close)];
    UIScrollView *scroll = [UIScrollView new]; scroll.translatesAutoresizingMaskIntoConstraints = NO; [self.view addSubview:scroll];
    UIStackView *stack = [UIStackView new]; stack.axis = UILayoutConstraintAxisVertical; stack.spacing = 16; stack.translatesAutoresizingMaskIntoConstraints = NO; [scroll addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[[scroll.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor], [scroll.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor], [scroll.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor], [scroll.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor], [stack.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:20], [stack.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-30], [stack.leadingAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.leadingAnchor constant:20], [stack.trailingAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.trailingAnchor constant:-20]]];
    UIVisualEffectView *banner = [[UIVisualEffectView alloc] initWithEffect:[UIBlurEffect effectWithStyle:UIBlurEffectStyleSystemMaterial]]; banner.layer.cornerRadius = 24; banner.clipsToBounds = YES;
    UILabel *title = [UILabel new]; title.text = @"狗头 · 私人聊天助手\n\n懂语气，也尊重边界\niOS 17 · 微信 8.0.75 适配诊断版"; title.numberOfLines = 0; title.font = [UIFont systemFontOfSize:22 weight:UIFontWeightSemibold]; title.translatesAutoresizingMaskIntoConstraints = NO; [banner.contentView addSubview:title];
    [NSLayoutConstraint activateConstraints:@[[title.topAnchor constraintEqualToAnchor:banner.topAnchor constant:24], [title.bottomAnchor constraintEqualToAnchor:banner.bottomAnchor constant:-24], [title.leadingAnchor constraintEqualToAnchor:banner.leadingAnchor constant:22], [title.trailingAnchor constraintEqualToAnchor:banner.trailingAnchor constant:-22]]]; [stack addArrangedSubview:banner];
    NSArray *names = @[@"✦  AI 助手\n模型 · 接口 · 人设", @"♡  此段关系\n阶段 · 目标 · 背景", @"↗  回复审核\n查看 · 修改 · 确认", @"≡  诊断日志\n兼容状态 · 清空"];
    for (NSUInteger i = 0; i < 4; i += 2) {
        UIStackView *row = [UIStackView new]; row.spacing = 14; row.distribution = UIStackViewDistributionFillEqually;
        for (NSUInteger j = i; j < i + 2; j++) {
            UIButton *b = [UIButton buttonWithType:UIButtonTypeSystem]; b.tag = j; b.backgroundColor = UIColor.secondarySystemGroupedBackgroundColor; b.layer.cornerRadius = 22; b.contentEdgeInsets = UIEdgeInsetsMake(24, 12, 24, 12); b.titleLabel.numberOfLines = 0; b.titleLabel.font = [UIFont systemFontOfSize:17 weight:UIFontWeightMedium]; [b setTitle:names[j] forState:UIControlStateNormal]; [b addTarget:self action:@selector(card:) forControlEvents:UIControlEventTouchUpInside]; [row addArrangedSubview:b];
        } [stack addArrangedSubview:row];
    }
    UILabel *footer = [UILabel new]; footer.text = @"默认关闭 · 主动授权上传 · 发送状态可追踪\n当前 .dylib 不含已验证的 8.0.75 实发适配"; footer.numberOfLines = 0; footer.font = [UIFont systemFontOfSize:13]; footer.textColor = UIColor.secondaryLabelColor; [stack addArrangedSubview:footer];
}
- (void)close { [self dismissViewControllerAnimated:YES completion:nil]; }
- (void)card:(UIButton *)button {
    if (button.tag == 0) [self.navigationController pushViewController:[GTSettings new] animated:YES];
    if (button.tag == 1) {
        if (!GTCoordinator.shared.currentPeer.length || !GTCoordinator.shared.account.length) { GTLog(@"open_supported_chat_and_receive_message_first"); return; }
        GTSettings *settings = [GTSettings new]; settings.scope = [GTCoordinator.shared scope:GTCoordinator.shared.currentPeer]; [self.navigationController pushViewController:settings animated:YES];
    }
    if (button.tag == 2) [GTCoordinator.shared review:GTCoordinator.shared.currentPeer host:self];
    if (button.tag == 3) {
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"脱敏诊断 · 无聊天正文" message:GTLogText() preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"关闭" style:UIAlertActionStyleCancel handler:nil]];
        [alert addAction:[UIAlertAction actionWithTitle:@"清空日志" style:UIAlertActionStyleDestructive handler:^(__unused UIAlertAction *a) { GTClearLogs(); }]];
        [alert addAction:[UIAlertAction actionWithTitle:@"复制诊断" style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a) { UIPasteboard.generalPasteboard.string = GTLogText(); }]];
        [self presentViewController:alert animated:YES completion:nil];
    }
}
@end
void GTPresent(UIViewController *host) { if (!host.presentedViewController) [host presentViewController:[[UINavigationController alloc] initWithRootViewController:[GTHome new]] animated:YES completion:nil]; }

static void (*GTOrigAppear)(id, SEL, BOOL);
@interface UIViewController (GoutouAI)
- (void)gt_openAI;
@end
@implementation UIViewController (GoutouAI)
- (void)gt_openAI { GTPresent(self); }
@end
@interface GTLauncher : NSObject
- (void)open:(UILongPressGestureRecognizer *)gesture;
@end
@implementation GTLauncher
- (void)open:(UILongPressGestureRecognizer *)gesture {
    if (gesture.state != UIGestureRecognizerStateBegan) return;
    UIViewController *host = gesture.view.window.rootViewController;
    while (host.presentedViewController) host = host.presentedViewController;
    if (host) GTPresent(host);
}
@end
static GTLauncher *GTLauncherInstance;
static void GTInstallPublicShortcut(void) {
    if (!GTLauncherInstance) GTLauncherInstance = [GTLauncher new];
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) if ([scene isKindOfClass:UIWindowScene.class]) {
        for (UIWindow *window in ((UIWindowScene *)scene).windows) if (window.isKeyWindow && !objc_getAssociatedObject(window, @selector(gt_openAI))) {
            UILongPressGestureRecognizer *gesture = [[UILongPressGestureRecognizer alloc] initWithTarget:GTLauncherInstance action:@selector(open:)];
            gesture.numberOfTouchesRequired = 3; gesture.minimumPressDuration = 1; gesture.cancelsTouchesInView = NO;
            [window addGestureRecognizer:gesture]; objc_setAssociatedObject(window, @selector(gt_openAI), gesture, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        }
    }
}
static void GTAppear(UIViewController *self, SEL cmd, BOOL animated) {
    GTOrigAppear(self, cmd, animated);
    NSString *name = NSStringFromClass(self.class);
    BOOL setting = [name isEqual:@"NewSettingViewController"], chat = [name isEqual:@"BaseMsgContentViewController"];
    if (!setting && !chat) return;
    if (chat) {
        // No fallback to title/display name: those are not unique identity keys.
        id contact = GTCall(self, @"GetContact", @[]);
        id peer = GTCall(contact, @"m_nsUsrName", @[]);
        GTCoordinator.shared.currentPeer = [peer isKindOfClass:NSString.class] ? peer : nil;
        if (!GTCoordinator.shared.currentPeer) GTLog(@"chat_identity_selector_unavailable");
    }
    for (UIBarButtonItem *item in self.navigationItem.rightBarButtonItems) if (item.action == @selector(gt_openAI)) return;
    NSMutableArray *items = [self.navigationItem.rightBarButtonItems mutableCopy] ?: [NSMutableArray new];
    [items addObject:[[UIBarButtonItem alloc] initWithTitle:@"AI" style:UIBarButtonItemStylePlain target:self action:@selector(gt_openAI)]];
    self.navigationItem.rightBarButtonItems = items;
}
__attribute__((constructor)) static void GTEntry(void) {
    if (![NSBundle.mainBundle.bundleIdentifier isEqual:@"com.tencent.xin"]) return;
    dispatch_async(dispatch_get_main_queue(), ^{
        Method m = class_getInstanceMethod(UIViewController.class, @selector(viewDidAppear:));
        GTOrigAppear = (void *)method_getImplementation(m); method_setImplementation(m, (IMP)GTAppear);
        GTInstallAdapter(); GTLog(@"plugin_loaded_0_1_0");
        GTInstallPublicShortcut();
        [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationDidBecomeActiveNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *note) { GTInstallPublicShortcut(); }];
    });
}
