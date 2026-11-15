import UIKit

@main final class Receiver: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication,didFinishLaunchingWithOptions options:[UIApplication.LaunchOptionsKey:Any]?) -> Bool {
        let window = UIWindow(frame:UIScreen.main.bounds); window.rootViewController = ReceiverController(); window.makeKeyAndVisible(); self.window = window; return true
    }
}
final class ReceiverController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad(); view.backgroundColor = .systemBackground
        let label = UILabel(); label.text = "另一个App：真实系统粘贴核验"; label.numberOfLines = 0
        let input = UITextView(); input.font = .systemFont(ofSize:24); input.backgroundColor = .secondarySystemBackground; input.accessibilityIdentifier = "receiverInput"
        let paste = UIPasteControl(configuration:UIPasteControl.Configuration()); paste.target = input; paste.accessibilityIdentifier = "receiverPaste"
        let stack = UIStackView(arrangedSubviews:[label,input,paste]); stack.axis = .vertical; stack.spacing = 24; stack.translatesAutoresizingMaskIntoConstraints = false; view.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.leadingAnchor,constant:24),stack.trailingAnchor.constraint(equalTo:view.safeAreaLayoutGuide.trailingAnchor,constant:-24),stack.topAnchor.constraint(equalTo:view.safeAreaLayoutGuide.topAnchor,constant:70),input.heightAnchor.constraint(equalToConstant:160)])
    }
}
