Why Use an Extension Instead?
Here’s why people sometimes choose to use an extension instead of configuring the proxy directly:

Handling Proxy Authentication:

When you use a proxy that requires a username and password, it’s a bit trickier to handle directly with just browser settings.
Extensions like the one in your code can easily handle authentication prompts by injecting the username and password automatically when a request is made (e.g., when a website asks for credentials).
More Flexibility:

Extensions can allow for more complex proxy management. For example, some extensions can handle:
Dynamic proxy switching based on conditions (e.g., changing the proxy after a certain amount of time).
Request filtering: The ability to block or redirect certain requests based on specific conditions.
Bypass certain websites: Some websites may need to be accessed directly without the proxy, which can be managed easily with an extension.
Automation and Convenience:

Extensions are typically more user-friendly and convenient for complex proxy setups. You don’t need to manually configure or write complex code. You just add the extension, and it manages everything for you.
This is especially helpful if the proxy settings might change or need frequent adjustments.
Avoiding Browser Detection:

Some websites may detect that you are using a proxy or automation tool (like Selenium). Using an extension might make the proxy setup less detectable since extensions can modify browser behavior in a way that looks more like a typical user interaction.
Separation of Concerns:

Using an extension isolates proxy handling from the main code, making it easier to manage, update, or swap out the proxy solution without modifying the main logic of your program.
In Summary:
You can use a proxy directly, but extensions are often preferred because they make it easier to handle authentication, manage complex proxy scenarios, and prevent detection of automation.
Extensions provide more control and convenience, especially when dealing with dynamic or complex proxy needs.





